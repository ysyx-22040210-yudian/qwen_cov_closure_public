#!/usr/bin/env python3
from __future__ import print_function

import argparse
import glob
import json
import os
import re
import runpy
import socket
import subprocess
import sys
import time

try:
    from urllib.request import Request, urlopen
except ImportError:
    Request = None
    urlopen = None


def shell_quote(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def bundled_base_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def bundled_root_dir():
    base = bundled_base_dir()
    candidates = [base, os.path.dirname(base)]
    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "models")):
            return candidate
        if os.path.exists(os.path.join(candidate, "bin", "ollama")):
            return candidate
        if os.path.exists(os.path.join(candidate, "bin", "ollama-linux-amd64")):
            return candidate
    return base


def ensure_executable(path):
    if not path or not os.path.exists(path):
        return
    if os.access(path, os.X_OK):
        return
    try:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | 0o111)
    except Exception:
        pass


def bundled_ollama_bin():
    root = bundled_root_dir()
    base = bundled_base_dir()
    candidates = [
        os.path.join(root, "bin", "ollama"),
        os.path.join(root, "bin", "ollama-linux-amd64"),
        os.path.join(base, "ollama"),
        os.path.join(base, "ollama-linux-amd64"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            ensure_executable(candidate)
            return candidate
    return ""


def bundled_ollama_models():
    root = bundled_root_dir()
    candidate = os.path.join(root, "models")
    if os.path.isdir(candidate):
        return candidate
    return ""


def ollama_library_paths(ollama_bin):
    if not ollama_bin or not os.path.isabs(ollama_bin):
        return []
    root = os.path.dirname(os.path.dirname(os.path.abspath(ollama_bin)))
    lib_root = os.path.join(root, "lib", "ollama")
    paths = []
    if os.path.isdir(lib_root):
        paths.append(lib_root)
        for name in ("cuda_v12", "cuda_v13", "mlx_cuda_v13", "vulkan"):
            candidate = os.path.join(lib_root, name)
            if os.path.isdir(candidate):
                paths.append(candidate)
    return paths


def apply_bundle_defaults(args):
    env_bin = os.environ.get("OLLAMA_BIN", "")
    bundled_bin = bundled_ollama_bin()
    if bundled_bin:
        args.ollama_bin = bundled_bin
    elif env_bin:
        args.ollama_bin = env_bin
    elif not args.ollama_bin:
        args.ollama_bin = "ollama"
    if not args.ollama_models:
        candidate = bundled_ollama_models()
        if candidate:
            args.ollama_models = candidate
        elif os.environ.get("OLLAMA_MODELS"):
            args.ollama_models = os.environ.get("OLLAMA_MODELS")
    if not args.ollama_host:
        args.ollama_host = os.environ.get("OLLAMA_HOST", "")


def print_ollama_resolution(args):
    print("Ollama auto-detected:")
    print("  command: {}".format(args.ollama_bin or "ollama"))
    print("  host: {}".format(args.ollama_host or "<auto>"))
    print("  models: {}".format(args.ollama_models or os.environ.get("OLLAMA_MODELS", "<system default>")))


def resolve_path(base_dir, path):
    if not path or str(path).lower() == "auto":
        return path
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def read_text(path, limit=0):
    with open(path, "r") as handle:
        text = handle.read()
    if limit and len(text) > limit:
        return text[:limit] + "\n... truncated ...\n"
    return text


def write_text(path, text):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w") as handle:
        handle.write(text)


def copy_text_file(src, dst):
    write_text(dst, read_text(src))


def command_exists(command):
    if not command:
        return False
    if os.path.exists(command):
        ensure_executable(command)
    if os.path.exists(command) and os.access(command, os.X_OK):
        return True
    try:
        subprocess.check_call("command -v {} >/dev/null 2>&1".format(shell_quote(command)), shell=True)
        return True
    except Exception:
        return False


def run_shell(command, cwd):
    print("$ " + command)
    return subprocess.check_call(command, shell=True, cwd=cwd)


def run_shell_status(command, cwd):
    try:
        return run_shell(command, cwd)
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1


def is_hgfs_path(path):
    return bool(path) and os.path.abspath(os.path.expanduser(path)).replace("\\", "/").startswith("/mnt/hgfs/")


def project_name_from_sim_dir(sim_dir):
    sim_dir = os.path.abspath(os.path.expanduser(sim_dir))
    parent = os.path.dirname(sim_dir) if os.path.basename(sim_dir) == "sim" else sim_dir
    return os.path.basename(parent.rstrip(os.sep)) or "project"


def local_sim_dir_for(sim_dir):
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, "ic_lab_runs", project_name_from_sim_dir(sim_dir) + "_cov_close", "sim")


def local_sim_matches_source(local_sim_dir, source_sim_dir):
    local_project = project_name_from_sim_dir(local_sim_dir)
    source_project = project_name_from_sim_dir(source_sim_dir)
    return local_project == source_project or local_project == source_project + "_cov_close" or local_project.startswith(source_project + "_")


def hgfs_source_sim_from_path(value):
    if not value:
        return ""
    text = str(value).strip().strip("'\"").replace("\\", "/")
    if not text.startswith("/mnt/hgfs/"):
        return ""
    parts = text.split("/")
    for idx, part in enumerate(parts):
        if part == "sim":
            return "/".join(parts[:idx + 1]) or "/"
    return ""


def infer_hgfs_source_sim_dir(args):
    for name in ("sim_dir", "cov_path", "dashboard", "grpinfo", "auto_script", "filelist", "qwen_hints", "ollama_log", "extra_context", "case_list"):
        source = hgfs_source_sim_from_path(getattr(args, name, ""))
        if source:
            return source
    return ""


def map_project_path(value, source_sim_dir, local_sim_dir):
    if not value:
        return value
    text = str(value).strip()
    if not text or text.lower() == "auto" or not os.path.isabs(text):
        return value
    source_sim_dir = os.path.abspath(os.path.expanduser(source_sim_dir))
    abs_value = os.path.abspath(os.path.expanduser(text))
    try:
        if abs_value == source_sim_dir or abs_value.startswith(source_sim_dir + os.sep):
            return os.path.normpath(os.path.join(local_sim_dir, os.path.relpath(abs_value, source_sim_dir)))
    except ValueError:
        pass
    return value


def map_project_text(value, source_sim_dir, local_sim_dir):
    if not value:
        return value
    source = os.path.abspath(os.path.expanduser(source_sim_dir)).replace("\\", "/").rstrip("/")
    local = os.path.abspath(os.path.expanduser(local_sim_dir)).replace("\\", "/").rstrip("/")
    return str(value).replace(source, local)


def path_is_under(path, parent):
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))
        abs_parent = os.path.abspath(os.path.expanduser(parent))
        return abs_path == abs_parent or abs_path.startswith(abs_parent.rstrip(os.sep) + os.sep)
    except Exception:
        return False


def looks_like_other_sim_path(value, sim_dir):
    if not value:
        return False
    text = str(value).strip()
    if not os.path.isabs(text) or path_is_under(text, sim_dir):
        return False
    normalized = os.path.abspath(os.path.expanduser(text)).replace("\\", "/")
    return "/sim/" in normalized and (normalized.startswith("/mnt/hgfs/") or "/ic_lab_runs/" in normalized)


def relativize_project_path(value, sim_dir):
    if not value:
        return value
    text = str(value).strip()
    if not text or text.lower() == "auto" or not os.path.isabs(text):
        return value
    if path_is_under(text, sim_dir):
        return os.path.relpath(os.path.abspath(os.path.expanduser(text)), sim_dir)
    return value


def sync_hgfs_project_to_local(source_sim_dir, local_sim_dir):
    if not command_exists("rsync"):
        raise RuntimeError("rsync is required to relocate HGFS projects to a local VM filesystem")
    parent = os.path.dirname(local_sim_dir)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    excludes = [
        "--exclude", "build/",
        "--exclude", "csrc/",
        "--exclude", "cov/",
        "--exclude", "logs/",
        "--exclude", "waves/",
        "--exclude", "simv*",
        "--exclude", "*.daidir",
        "--exclude", "*.vdb",
        "--exclude", "DVEfiles/",
        "--exclude", "64/",
        "--exclude", "ucli.key",
        "--exclude", "cm.log",
        "--exclude", "verdiLog",
        "--exclude", "novas.*",
    ]
    command = ["rsync", "-a"] + excludes + [
        os.path.abspath(source_sim_dir).rstrip(os.sep) + os.sep,
        os.path.abspath(local_sim_dir).rstrip(os.sep) + os.sep,
    ]
    print("Detected HGFS sim directory: {}".format(source_sim_dir))
    print("VCS compile/link needs a local Linux filesystem; syncing project to: {}".format(local_sim_dir))
    subprocess.check_call(command)


def relocate_hgfs_args(args):
    requested_sim_dir = os.path.abspath(os.path.expanduser(args.sim_dir or "."))
    source_sim_dir = ""
    if is_hgfs_path(requested_sim_dir):
        source_sim_dir = hgfs_source_sim_from_path(requested_sim_dir) or requested_sim_dir
    else:
        source_sim_dir = infer_hgfs_source_sim_dir(args)
    if not source_sim_dir:
        args.sim_dir = requested_sim_dir
        return requested_sim_dir
    if args.no_local_relocate:
        print("Warning: running from HGFS path {}; VCS may fail during shared-object link.".format(source_sim_dir), file=sys.stderr)
        args.sim_dir = source_sim_dir
        return source_sim_dir
    if is_hgfs_path(requested_sim_dir):
        local_sim_dir = local_sim_dir_for(source_sim_dir)
    else:
        if os.path.basename(requested_sim_dir.rstrip(os.sep)) == "sim" and local_sim_matches_source(requested_sim_dir, source_sim_dir):
            local_sim_dir = requested_sim_dir
        else:
            local_sim_dir = local_sim_dir_for(source_sim_dir)
            print("Input paths point to project '{}' but --sim-dir is '{}'; switching to local run directory '{}'.".format(project_name_from_sim_dir(source_sim_dir), requested_sim_dir, local_sim_dir))
    sync_hgfs_project_to_local(source_sim_dir, local_sim_dir)
    for name in ("cov_path", "dashboard", "grpinfo", "auto_script", "filelist", "qwen_hints", "ollama_log", "extra_context", "case_list"):
        setattr(args, name, map_project_path(getattr(args, name), source_sim_dir, local_sim_dir))
    for name in ("pre_run", "run_case", "post_run", "compile_cmd", "regress_cmd"):
        setattr(args, name, map_project_text(getattr(args, name), source_sim_dir, local_sim_dir))
    args.sim_dir = local_sim_dir
    print("Project paths under HGFS were mapped to the local run directory.")
    return local_sim_dir


def normalize_case_list_format(value):
    value = str(value).strip()
    if valid_case_list_format(value):
        return value
    normalized = value.replace("\\", "/")
    if "/" in normalized and "." not in os.path.basename(normalized):
        return os.path.join(os.path.dirname(normalized), "{case}").replace("\\", "/")
    return value


def valid_case_list_format(value):
    value = str(value).strip()
    if not value or value.lower() == "auto":
        return True
    allowed = [
        "{case}",
        "{case_file}",
        "{case_file_no_ext}",
        "{case_file_rel}",
        "{case_file_rel_no_ext}",
        "{case_file_abs}",
        "{case_file_abs_no_ext}",
        "{case_file_basename}",
        "{case_file_basename_no_ext}",
        "{cases_dir}",
        "{cases_dir_abs}",
        "{case_dir}",
        "{case_dir_abs}",
        "{case_in_file}",
        "{index}",
        "{index1}",
    ]
    return any(token in value for token in allowed)


def infer_cases_dir_from_case_list_format(line_format):
    for token in str(line_format or "").strip().split():
        normalized = token.replace("\\", "/")
        if "{" not in normalized or "}" not in normalized or "/" not in normalized:
            continue
        parent = os.path.dirname(normalized)
        if parent and "{" not in parent and "}" not in parent:
            return parent.replace("\\", "/")
    return ""


def line_format_uses_case_file(line_format):
    text = str(line_format or "")
    return "{case_file" in text


def line_format_uses_bare_case(line_format):
    text = str(line_format or "")
    return "{case}" in text and not line_format_uses_case_file(text)


def relpath_if_under(path, root):
    path = os.path.abspath(path)
    root = os.path.abspath(root)
    if path_is_under(path, root):
        return os.path.relpath(path, root)
    return path


def template_case_root(sim_dir, template_case):
    resolved = resolve_path(sim_dir, template_case)
    root = os.path.dirname(os.path.abspath(resolved))
    return relpath_if_under(root, sim_dir).replace("\\", "/")


def join_case_root_and_lst_parent(case_root, lst_parent):
    case_root = str(case_root or "").replace("\\", "/").strip("/")
    lst_parent = str(lst_parent or "").replace("\\", "/").strip("/")
    if not lst_parent:
        return case_root
    if os.path.isabs(lst_parent):
        return lst_parent
    if case_root:
        root_base = os.path.basename(case_root.rstrip("/"))
        if lst_parent == case_root or lst_parent.startswith(case_root + "/"):
            return lst_parent
        if root_base and (lst_parent == root_base or lst_parent.startswith(root_base + "/")):
            parent_tail = lst_parent[len(root_base):].lstrip("/")
            return os.path.join(os.path.dirname(case_root), root_base, parent_tail).replace("\\", "/").rstrip("/")
        return os.path.join(case_root, lst_parent).replace("\\", "/")
    return lst_parent


def path_component_list(path):
    text = str(path or "").replace("\\", "/").strip("/")
    if not text:
        return []
    return [item for item in text.split("/") if item]


def path_has_component_suffix(path, suffix):
    path_parts = path_component_list(path)
    suffix_parts = path_component_list(suffix)
    if not suffix_parts or len(path_parts) < len(suffix_parts):
        return False
    return path_parts[-len(suffix_parts):] == suffix_parts


def strip_component_suffix(path, suffix):
    if not path_has_component_suffix(path, suffix):
        return ""
    path_text = str(path or "").replace("\\", "/").rstrip("/")
    suffix_parts = path_component_list(suffix)
    path_parts = path_component_list(path_text)
    keep = path_parts[:len(path_parts) - len(suffix_parts)]
    if not keep:
        if os.path.isabs(path_text):
            return os.path.sep
        return "."
    prefix = os.path.sep if os.path.isabs(path_text) else ""
    return (prefix + "/".join(keep)).replace("\\", "/")


def join_cases_dir_and_lst_parent(cases_dir, lst_parent):
    cases_dir = str(cases_dir or "").replace("\\", "/").rstrip("/")
    lst_parent = str(lst_parent or "").replace("\\", "/").strip("/")
    if not lst_parent:
        return cases_dir
    if os.path.isabs(lst_parent):
        return lst_parent
    if not cases_dir:
        return lst_parent
    if path_has_component_suffix(cases_dir, lst_parent):
        return cases_dir
    base = os.path.basename(cases_dir.rstrip("/"))
    if base and (lst_parent == base or lst_parent.startswith(base + "/")):
        return os.path.join(os.path.dirname(cases_dir), lst_parent).replace("\\", "/").rstrip("/")
    return os.path.join(cases_dir, lst_parent).replace("\\", "/")


def expected_generated_cases_dir(args, sim_dir):
    inferred = infer_cases_dir_from_case_list_format(args.case_list_format)
    if inferred:
        return join_cases_dir_and_lst_parent(args.cases_dir or template_case_root(sim_dir, args.template_case) or "cases", inferred)
    return args.cases_dir or template_case_root(sim_dir, args.template_case) or "cases"


def expected_case_root_for_lst(args, sim_dir):
    inferred = infer_cases_dir_from_case_list_format(args.case_list_format)
    if inferred:
        stripped = strip_component_suffix(expected_generated_cases_dir(args, sim_dir), inferred)
        return stripped or template_case_root(sim_dir, args.template_case) or "."
    if line_format_uses_bare_case(args.case_list_format):
        return expected_generated_cases_dir(args, sim_dir)
    return template_case_root(sim_dir, args.template_case) or os.path.dirname(expected_generated_cases_dir(args, sim_dir)) or "."


def expected_case_list_path(args, sim_dir):
    case_list = args.case_list or ""
    if not case_list:
        return ""
    if os.path.isabs(case_list):
        return case_list
    normalized = case_list.replace("\\", "/")
    if args.case_list_dir and "/" not in normalized and "\\" not in case_list:
        return os.path.join(args.case_list_dir, case_list).replace("\\", "/")
    return case_list


def first_existing_file(candidates):
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def candidate_template_from_dir(directory):
    preferred = [
        "tc_func_cov_template.in",
        "tc_full_pipeline_random.in",
        "tc_bright_sub.in",
        "tc_drop_blue.in",
    ]
    candidates = [os.path.join(directory, name) for name in preferred]
    candidates.extend(sorted(glob.glob(os.path.join(directory, "tc_*.in"))))
    return first_existing_file(candidates)


def sanitize_template_case(args, sim_dir):
    original = args.template_case
    resolved = resolve_path(sim_dir, original)
    if os.path.isfile(resolved):
        return original

    candidates = []
    if os.path.isfile(resolved + ".in"):
        candidates.append(resolved + ".in")
    if os.path.isdir(resolved):
        selected = candidate_template_from_dir(resolved)
        if selected:
            candidates.append(selected)
    parent = os.path.dirname(resolved)
    if os.path.basename(resolved).lower() == "case":
        candidates.append(candidate_template_from_dir(os.path.join(parent, "cases")))
    candidates.append(candidate_template_from_dir(resolve_path(sim_dir, "cases")))
    selected = first_existing_file(candidates)
    if selected:
        suggested = relativize_project_path(selected, sim_dir)
        print("Template case '{}' is not an existing file. Candidate found: '{}'.".format(original, suggested))
        if args.interactive:
            answer = prompt_value("Use this candidate template case? y/n", "n")
            if truthy(answer):
                return suggested
        print("Keeping user-provided template case unchanged.")
    return original


def sanitize_cases_dir(args, sim_dir):
    value = args.cases_dir
    if value:
        return value
    return "cases/auto_llama"


def sanitize_project_args(args, sim_dir):
    if args.case_list_format:
        args.case_list_format = normalize_case_list_format(args.case_list_format)
    if looks_like_other_sim_path(args.cov_path, sim_dir):
        print("Coverage path '{}' is outside active sim directory '{}'; using 'cov'.".format(args.cov_path, sim_dir))
        args.cov_path = "cov"
    for name in ("cov_path", "dashboard", "grpinfo", "auto_script", "filelist", "qwen_hints", "ollama_log", "extra_context", "case_list"):
        setattr(args, name, relativize_project_path(getattr(args, name), sim_dir))
    args.cases_dir = sanitize_cases_dir(args, sim_dir)
    if not args.case_list_dir:
        args.case_list_dir = "."
    args.template_case = sanitize_template_case(args, sim_dir)
    args.auto_script = prepare_auto_script(args, sim_dir)


def prepare_auto_script(args, sim_dir):
    if getattr(sys, "frozen", False):
        bundled = os.path.join(bundled_base_dir(), "auto_func_cov.py")
        if os.path.exists(bundled):
            target = resolve_path(sim_dir, "logs/auto_func_cov_runtime.py")
            copy_text_file(bundled, target)
            print("Runtime auto_func_cov.py extracted to {}".format(os.path.relpath(target, sim_dir)))
        return "__bundled_auto_func_cov__"
    value = args.auto_script or "scripts/auto_func_cov.py"
    candidate = resolve_path(sim_dir, value)
    if os.path.exists(candidate):
        return relativize_project_path(candidate, sim_dir)
    bundled = os.path.join(bundled_base_dir(), "auto_func_cov.py")
    if os.path.exists(bundled):
        target = resolve_path(sim_dir, "logs/auto_func_cov_runtime.py")
        copy_text_file(bundled, target)
        print("Runtime auto_func_cov.py extracted to {}".format(os.path.relpath(target, sim_dir)))
        return os.path.relpath(target, sim_dir)
    sibling = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "auto_func_cov.py")
    if os.path.exists(sibling):
        target = resolve_path(sim_dir, "logs/auto_func_cov_runtime.py")
        copy_text_file(sibling, target)
        print("Runtime auto_func_cov.py copied to {}".format(os.path.relpath(target, sim_dir)))
        return os.path.relpath(target, sim_dir)
    print("Warning: auto_func_cov.py not found at '{}' and no bundled copy was available.".format(value), file=sys.stderr)
    return value


def auto_func_cov_entry_path():
    bundled = os.path.join(bundled_base_dir(), "auto_func_cov.py")
    if os.path.exists(bundled):
        return bundled
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_func_cov.py")
    if os.path.exists(local):
        return local
    sibling = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "auto_func_cov.py")
    if os.path.exists(sibling):
        return sibling
    return ""


def run_auto_func_cov_entry():
    script = auto_func_cov_entry_path()
    if not script:
        print("Bundled auto_func_cov.py was not found. Rebuild the executable with auto_func_cov.py included.", file=sys.stderr)
        return 127
    sys.argv = [script] + sys.argv[2:]
    runpy.run_path(script, run_name="__main__")
    return 0


def python_command():
    return os.environ.get("PYTHON_FOR_QWEN_COV") or os.environ.get("QWEN_COV_PYTHON") or sys.executable or "python3"


ARG_REVIEW_FIELDS = [
    "sim_dir",
    "template_case",
    "cov_path",
    "cases_dir",
    "case_list",
    "case_list_dir",
    "case_list_format",
    "case_in_file",
    "compile_cmd",
    "regress_cmd",
    "max_iterations",
    "max_cross_cases",
    "target",
    "urg_cmd",
]


def snapshot_args(args):
    data = {}
    for name in ARG_REVIEW_FIELDS:
        data[name] = str(getattr(args, name, "") or "")
    return data


def arg_changes(before, args):
    changes = []
    for name in ARG_REVIEW_FIELDS:
        old = before.get(name, "")
        new = str(getattr(args, name, "") or "")
        if old != new:
            changes.append((name, old, new))
    return changes


def confirm_arg_changes(args, before, title="Input corrections"):
    changes = arg_changes(before, args)
    if not changes:
        return True
    print("")
    print(title + ":")
    for name, old, new in changes:
        print("  {}:".format(name))
        print("    input : {}".format(old if old else "<empty>"))
        print("    use   : {}".format(new if new else "<empty>"))
    print("")
    if not args.interactive:
        print("Non-interactive mode: applying the corrections above.")
        return True
    answer = prompt_value("Apply these corrections and continue? y/n", "y")
    if truthy(answer):
        return True
    print("Canceled before running because corrected inputs were not confirmed.")
    return False


def resolve_model(choice, model):
    aliases = {
        "qwen": "qwen3.5:9b-q4_K_M",
        "qwen3": "qwen3.5:9b-q4_K_M",
        "qwen3-9b": "qwen3.5:9b-q4_K_M",
        "qwen3.5": "qwen3.5:9b-q4_K_M",
        "llama": "llama3:8b-instruct-q4_K_M",
        "llama3": "llama3:8b-instruct-q4_K_M",
        "llama3-8b": "llama3:8b-instruct-q4_K_M",
    }
    selected = choice or model
    return aliases.get(selected, selected)


def normalize_ollama_host(host):
    if not host:
        host = "127.0.0.1:11434"
    if not host.startswith("http://") and not host.startswith("https://"):
        host = "http://" + host
    return host.rstrip("/")


def denormalize_ollama_host(host):
    text = normalize_ollama_host(host)
    if text.startswith("http://"):
        return text[len("http://"):]
    if text.startswith("https://"):
        return text[len("https://"):]
    return text


def ollama_host_candidates(args):
    candidates = []
    for value in (args.ollama_host, os.environ.get("OLLAMA_HOST", "")):
        if value:
            candidates.append(value)
    for port in (11434, 11435, 11436, 11534, 11666):
        candidates.append("127.0.0.1:{}".format(port))
    seen = set()
    result = []
    for candidate in candidates:
        normalized = normalize_ollama_host(candidate)
        if normalized not in seen:
            seen.add(normalized)
            result.append(candidate)
    return result


def first_ready_ollama_host(args):
    for host in ollama_host_candidates(args):
        if ollama_ready(host, 1):
            return denormalize_ollama_host(host)
    return ""


def port_is_available(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        sock.bind((host, int(port)))
        return True
    except Exception:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def choose_ollama_host(args):
    ready = first_ready_ollama_host(args)
    if ready:
        return ready
    for candidate in ollama_host_candidates(args):
        host_port = denormalize_ollama_host(candidate).split("/", 1)[0]
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
        else:
            host, port = host_port, "11434"
        if host in ("localhost", "0.0.0.0", ""):
            host = "127.0.0.1"
        if port_is_available(host, port):
            return "{}:{}".format(host, port)
    return "127.0.0.1:11434"


def ollama_ready(host, timeout_sec):
    if Request is None:
        return False
    try:
        req = Request(normalize_ollama_host(host) + "/api/tags")
        urlopen(req, timeout=timeout_sec).read()
        return True
    except Exception:
        return False


def start_ollama_server(args, sim_dir):
    args.ollama_host = choose_ollama_host(args)
    if not command_exists(args.ollama_bin):
        return False
    print_ollama_resolution(args)
    if ollama_ready(args.ollama_host, 3):
        return True
    env = os.environ.copy()
    env["OLLAMA_HOST"] = args.ollama_host
    if args.ollama_models:
        env["OLLAMA_MODELS"] = args.ollama_models
    lib_paths = ollama_library_paths(args.ollama_bin)
    if lib_paths:
        current_ld = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ":".join(lib_paths + ([current_ld] if current_ld else []))
    log_path = resolve_path(sim_dir, args.ollama_log)
    parent = os.path.dirname(log_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(log_path, "ab") as log:
        subprocess.Popen([args.ollama_bin, "serve"], stdout=log, stderr=log, env=env)
    for _ in range(20):
        if ollama_ready(args.ollama_host, 2):
            return True
        time.sleep(1)
    return False


def ask_ollama(args, prompt):
    if Request is None:
        raise RuntimeError("urllib.request is unavailable")
    payload = json.dumps({"model": args.model, "prompt": prompt, "stream": False, "options": {"num_predict": args.qwen_num_predict}}).encode("utf-8")
    req = Request(normalize_ollama_host(args.ollama_host) + "/api/generate", data=payload, headers={"Content-Type": "application/json"})
    data = json.loads(urlopen(req, timeout=args.qwen_timeout).read().decode("utf-8", "replace"))
    return data.get("response", "")


def extract_json_object(text):
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def valid_alias_target(value):
    return str(value).strip().lower() not in set(["case_name", "random_seed", "profile", "frame_count"])


def normalize_hints(data):
    hints = {"aliases": {}, "constraints": [], "notes": []}
    aliases = data.get("aliases", {}) if isinstance(data, dict) else {}
    if isinstance(aliases, dict):
        for key, value in aliases.items():
            if key and value and valid_alias_target(value):
                hints["aliases"][str(key)] = str(value)
    constraints = data.get("constraints", []) if isinstance(data, dict) else []
    if isinstance(constraints, list):
        for item in constraints:
            if not isinstance(item, dict):
                continue
            lhs = item.get("lhs") or item.get("left") or item.get("item")
            rhs = item.get("rhs") or item.get("right") or item.get("peer")
            op = item.get("op") or item.get("operator")
            if lhs and rhs and str(op).strip() in ("<", "<=", ">", ">=", "==", "=", "!=", "lt", "le", "gt", "ge", "eq", "ne"):
                hints["constraints"].append({"lhs": str(lhs), "op": str(op), "rhs": str(rhs)})
    notes = data.get("notes", []) if isinstance(data, dict) else []
    if isinstance(notes, list):
        hints["notes"] = [str(note) for note in notes[:20]]
    elif isinstance(notes, str):
        hints["notes"] = [notes]
    for key in ("case_list_format", "lst_format", "case_lst_format"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, str) and value.strip():
            normalized = normalize_case_list_format(value)
            if valid_case_list_format(normalized):
                hints["case_list_format"] = normalized
                break
    if isinstance(data, dict):
        hints["need_code_edit"] = bool(data.get("need_code_edit", False))
        reason = data.get("code_edit_reason", "")
        patch = data.get("code_patch", "")
        if isinstance(reason, str):
            hints["code_edit_reason"] = reason
        if isinstance(patch, str):
            hints["code_patch"] = patch
    return hints


def parse_case_items(template_path):
    items = []
    if not template_path or not os.path.exists(template_path):
        return items
    for raw in read_text(template_path).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        items.append(line.split()[0])
    return items


def normalize_code_name(name):
    name = str(name or "").strip()
    name = re.sub("[^A-Za-z0-9_$]+", "_", name)
    name = name.strip("_").lower()
    if name.startswith("cp_"):
        name = name[3:]
    return name


def compact_code_name(name):
    return re.sub("[^a-z0-9]+", "", normalize_code_name(name))


def coverpoint_to_item_name(name):
    return normalize_code_name(name)


def project_root_from_sim_dir(sim_dir):
    sim_dir = os.path.abspath(os.path.expanduser(sim_dir))
    if os.path.basename(sim_dir.rstrip(os.sep)) == "sim":
        return os.path.dirname(sim_dir.rstrip(os.sep))
    return sim_dir


def discover_code_files(sim_dir):
    root = project_root_from_sim_dir(sim_dir)
    skip_dirs = set(["build", "logs", "cov", "waves", "csrc", "__pycache__", "DVEfiles", "64", ".git"])
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        base = os.path.basename(dirpath)
        if base.startswith("cov") or base.endswith(".vdb") or base.endswith(".daidir"):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith("cov")]
        for filename in filenames:
            if filename.endswith((".sv", ".svh", ".v", ".vh")):
                files.append(os.path.join(dirpath, filename))
    return sorted(files)


def strip_sv_comment(line):
    pos = line.find("//")
    return line[:pos] if pos >= 0 else line


def scan_code_symbols(sim_dir):
    coverpoints = []
    crosses = []
    cp_to_item = {}
    cp_pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_$]*)\s*:\s*coverpoint\s+([^;{]+)")
    cross_pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_$]*)\s*:\s*cross\s+([^;{]+)")
    for path in discover_code_files(sim_dir):
        rel = os.path.relpath(path, sim_dir)
        try:
            lines = read_text(path).splitlines()
        except Exception:
            continue
        for idx, raw in enumerate(lines, 1):
            line = strip_sv_comment(raw)
            match = cp_pattern.search(line)
            if match:
                name, expr = match.groups()
                item = coverpoint_to_item_name(name)
                cp_to_item[name] = item
                coverpoints.append({"name": name, "item": item, "expr": expr.strip(), "file": rel, "line": idx})
        for idx, raw in enumerate(lines, 1):
            line = strip_sv_comment(raw)
            match = cross_pattern.search(line)
            if not match:
                continue
            name, body = match.groups()
            refs = []
            items = []
            for token in body.split(","):
                token = re.sub(r"\s+.*$", "", token.strip())
                if not token:
                    continue
                refs.append(token)
                items.append(cp_to_item.get(token, coverpoint_to_item_name(token)))
            crosses.append({"name": name, "refs": refs, "items": items, "file": rel, "line": idx})
    return coverpoints, crosses


def line_matches_item(line, item):
    item_norm = normalize_code_name(item)
    item_compact = compact_code_name(item)
    if not item_norm:
        return False
    if re.search(r"\b{}\b".format(re.escape(str(item))), line):
        return True
    line_norm = normalize_code_name(line)
    if re.search(r"\b{}\b".format(re.escape(item_norm)), line_norm):
        return True
    return item_compact and item_compact in compact_code_name(line)


def find_item_references(sim_dir, items, max_refs_per_item=12):
    refs = {}
    for item in items:
        refs[item] = []
    if not items:
        return refs
    for path in discover_code_files(sim_dir):
        rel = os.path.relpath(path, sim_dir)
        try:
            lines = read_text(path).splitlines()
        except Exception:
            continue
        for idx, raw in enumerate(lines, 1):
            body = strip_sv_comment(raw)
            if not body.strip():
                continue
            for item in items:
                if len(refs[item]) >= max_refs_per_item:
                    continue
                if line_matches_item(body, item):
                    refs[item].append({"file": rel, "line": idx, "text": body.strip()[:220]})
    return refs


def apply_alias_to_item(name, hints):
    aliases = hints.get("aliases", {}) if hints else {}
    if isinstance(aliases, dict):
        if name in aliases:
            return normalize_code_name(aliases[name])
        norm = normalize_code_name(name)
        if norm in aliases:
            return normalize_code_name(aliases[norm])
    return normalize_code_name(name)


def build_code_mapping(args, sim_dir, hints=None):
    template_path = resolve_path(sim_dir, args.template_case)
    case_items = parse_case_items(template_path)
    coverpoints, crosses = scan_code_symbols(sim_dir)
    refs_by_item = find_item_references(sim_dir, case_items)
    cp_by_item = {}
    for cp in coverpoints:
        item = apply_alias_to_item(cp["name"], hints) or cp.get("item", "")
        cp_by_item.setdefault(item, []).append(cp)

    used_cp_names = set()
    item_rows = []
    for item in case_items:
        item_norm = normalize_code_name(item)
        cps = list(cp_by_item.get(item_norm, []))
        if not cps:
            item_compact = compact_code_name(item)
            for cp_item, cp_list in cp_by_item.items():
                if item_compact and item_compact == compact_code_name(cp_item):
                    cps.extend(cp_list)
        for cp in cps:
            used_cp_names.add(cp["name"])
        refs = refs_by_item.get(item, [])
        status = "matched"
        if not cps and not refs:
            status = "missing_code_reference"
        elif not cps:
            status = "code_only_no_coverpoint"
        item_rows.append({"item": item, "normalized": item_norm, "status": status, "coverpoints": cps[:8], "references": refs})

    unmatched_coverpoints = [cp for cp in coverpoints if cp["name"] not in used_cp_names]
    mapping = {
        "template_case": args.template_case,
        "template_case_resolved": template_path,
        "sim_dir": sim_dir,
        "items": item_rows,
        "coverpoints": coverpoints,
        "crosses": crosses,
        "unmatched_case_items": [row["item"] for row in item_rows if row["status"] == "missing_code_reference"],
        "case_items_without_coverpoints": [row["item"] for row in item_rows if row["status"] == "code_only_no_coverpoint"],
        "unmatched_coverpoints": unmatched_coverpoints,
    }
    return mapping


def md_escape(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def write_code_mapping(args, sim_dir, mapping):
    json_path = resolve_path(sim_dir, args.code_map)
    md_path = resolve_path(sim_dir, args.code_map_md)
    write_text(json_path, json.dumps(mapping, indent=2, sort_keys=True) + "\n")
    lines = [
        "# Case Item Code Map",
        "",
        "Template case: `{}`".format(mapping.get("template_case", "")),
        "",
        "| Case item | Status | Coverpoint(s) | Code reference(s) |",
        "|---|---|---|---|",
    ]
    for row in mapping.get("items", []):
        cps = ", ".join([cp["name"] for cp in row.get("coverpoints", [])]) or "-"
        refs = []
        for ref in row.get("references", [])[:4]:
            refs.append("{}:{}".format(ref.get("file", ""), ref.get("line", "")))
        lines.append("| {} | {} | {} | {} |".format(md_escape(row.get("item", "")), md_escape(row.get("status", "")), md_escape(cps), md_escape(", ".join(refs) or "-")))
    if mapping.get("unmatched_coverpoints"):
        lines.extend(["", "## Unmatched Coverpoints", ""])
        for cp in mapping.get("unmatched_coverpoints", [])[:80]:
            lines.append("- `{}` at `{}`:{}".format(cp.get("name", ""), cp.get("file", ""), cp.get("line", "")))
    write_text(md_path, "\n".join(lines) + "\n")
    print("Case/code mapping written to {} and {}".format(os.path.relpath(json_path, sim_dir), os.path.relpath(md_path, sim_dir)))


def print_code_mapping_summary(mapping, limit=20):
    items = mapping.get("items", [])
    missing_refs = mapping.get("unmatched_case_items", [])
    no_cp = mapping.get("case_items_without_coverpoints", [])
    unmatched_cp = mapping.get("unmatched_coverpoints", [])
    matched = [row for row in items if row.get("status") == "matched"]
    print("Case/code mapping summary: total_case_items={} matched_to_coverpoint={} missing_code_refs={} code_refs_but_no_coverpoint={} unmatched_coverpoints={}".format(len(items), len(matched), len(missing_refs), len(no_cp), len(unmatched_cp)))
    if matched:
        print("  Case items matched to coverpoints:")
        for row in matched[:limit]:
            cps = ", ".join(cp.get("name", "") for cp in row.get("coverpoints", [])[:3] if cp.get("name"))
            print("    {} -> {}".format(row.get("item", ""), cps or "<matched>"))
        if len(matched) > limit:
            print("    ... {} more".format(len(matched) - limit))
    if missing_refs:
        print("  Case items without obvious code references:")
        for item in missing_refs[:limit]:
            print("    {}".format(item))
    if no_cp:
        print("  Informational: case items with code references but no matching coverpoint:")
        for item in no_cp[:limit]:
            print("    {}".format(item))
    if unmatched_cp:
        print("  Coverpoints not matched to template items:")
        for cp in unmatched_cp[:limit]:
            print("    {} at {}:{}".format(cp.get("name", ""), cp.get("file", ""), cp.get("line", "")))


def code_mapping_prompt(mapping, limit):
    slim = {
        "template_case": mapping.get("template_case", ""),
        "items": [],
        "unmatched_case_items": mapping.get("unmatched_case_items", []),
        "case_items_without_coverpoints": mapping.get("case_items_without_coverpoints", []),
        "unmatched_coverpoints": [{"name": cp.get("name"), "item": cp.get("item"), "file": cp.get("file"), "line": cp.get("line")} for cp in mapping.get("unmatched_coverpoints", [])[:80]],
        "crosses": mapping.get("crosses", [])[:80],
    }
    for row in mapping.get("items", []):
        slim["items"].append({
            "item": row.get("item"),
            "status": row.get("status"),
            "coverpoints": [cp.get("name") for cp in row.get("coverpoints", [])],
            "references": [{"file": ref.get("file"), "line": ref.get("line"), "text": ref.get("text")} for ref in row.get("references", [])[:4]],
        })
    text = json.dumps(slim, indent=2, sort_keys=True)
    if limit and len(text) > limit:
        text = text[:limit] + "\n... truncated ...\n"
    return text


def build_prompt(args, sim_dir, code_mapping=None):
    parts = [
        "Return exactly one JSON object for adapting config-file driven functional coverage closure.",
        "Schema: {\"aliases\":{\"coverpoint_or_signal\":\"case_item\"},\"constraints\":[{\"lhs\":\"case_item\",\"op\":\"<|<=|>|>=|==|!=\",\"rhs\":\"case_item\"}],\"case_list_format\":\"{case_file}\",\"notes\":[\"short note\"],\"need_code_edit\":false,\"code_edit_reason\":\"\",\"code_patch\":\"\"}",
        "Only include aliases and constraints supported by provided project evidence.",
        "For each case item, use the code mapping to decide whether it already maps to code/coverpoints. If code edit is necessary, code_patch must be a unified diff relative to the active sim directory or project root. Prefer testbench/coverage/config parsing glue changes; do not modify DUT RTL unless the evidence clearly requires it.",
    ]
    template_path = resolve_path(sim_dir, args.template_case)
    if os.path.exists(template_path):
        parts.append("Template case:\n" + read_text(template_path, args.context_limit))
        parts.append("Template item names:\n" + "\n".join(parse_case_items(template_path)))
    if code_mapping:
        parts.append("Case item to code mapping:\n" + code_mapping_prompt(code_mapping, args.context_limit))
    for label, path in (("Filelist", args.filelist), ("Extra context", args.extra_context)):
        full = resolve_path(sim_dir, path)
        if full and os.path.exists(full):
            parts.append(label + ":\n" + read_text(full, args.context_limit))
    if args.case_list_format:
        parts.append("User-provided lst format:\n" + args.case_list_format)
    return "\n\n".join(parts)


def extract_unified_diff(text):
    if not text:
        return ""
    marker = "diff --git "
    idx = text.find(marker)
    if idx >= 0:
        return text[idx:].strip() + "\n"
    marker = "--- "
    idx = text.find(marker)
    if idx >= 0:
        return text[idx:].strip() + "\n"
    return ""


def diff_paths_are_safe(patch_text, sim_dir):
    root = project_root_from_sim_dir(sim_dir)
    paths = []
    for raw in patch_text.splitlines():
        if raw.startswith("diff --git "):
            parts = raw.split()
            for token in parts[2:4]:
                if token.startswith("a/") or token.startswith("b/"):
                    paths.append(token[2:])
        elif raw.startswith("--- ") or raw.startswith("+++ "):
            token = raw.split(None, 1)[1].strip()
            if token == "/dev/null":
                continue
            if token.startswith("a/") or token.startswith("b/"):
                token = token[2:]
            paths.append(token)
    for path in paths:
        if not path or path == "/dev/null":
            continue
        abs_path = path if os.path.isabs(path) else os.path.abspath(os.path.join(root, path))
        if not path_is_under(abs_path, root):
            print("Rejecting code patch because path is outside project: {}".format(path))
            return False
    return True


def apply_code_patch(args, sim_dir, patch_text):
    patch_text = extract_unified_diff(patch_text)
    if not patch_text:
        print("LLM requested code edit but did not provide a usable unified diff.")
        return False
    if not diff_paths_are_safe(patch_text, sim_dir):
        return False
    patch_path = resolve_path(sim_dir, args.code_patch_file)
    write_text(patch_path, patch_text)
    print("LLM code patch written to {}".format(os.path.relpath(patch_path, sim_dir)))
    if not args.interactive and not args.apply_llm_patch:
        print("Non-interactive mode: patch was not applied. Re-run with --apply-llm-patch to apply it.")
        return False
    if args.interactive:
        reason = getattr(args, "_llm_code_edit_reason", "")
        if reason:
            print("LLM code edit reason: {}".format(reason))
        answer = prompt_value("Apply this LLM patch now? y/n", "n")
        if not truthy(answer):
            print("Patch not applied.")
            return False
    root = project_root_from_sim_dir(sim_dir)
    command = "patch -p1 < {}".format(shell_quote(patch_path))
    rc = run_shell_status(command, root)
    if rc:
        print("Patch command failed with exit status {}. Patch kept at {}.".format(rc, os.path.relpath(patch_path, sim_dir)))
        return False
    print("Patch applied. Please review the changed files before trusting results.")
    return True


def maybe_apply_llm_code_edit(args, sim_dir, qwen_hints):
    if not qwen_hints.get("need_code_edit"):
        return False
    args._llm_code_edit_reason = qwen_hints.get("code_edit_reason", "")
    if args._llm_code_edit_reason:
        print("LLM reports code edit may be needed: {}".format(args._llm_code_edit_reason))
    return apply_code_patch(args, sim_dir, qwen_hints.get("code_patch", ""))


def truthy(value):
    return str(value).strip().lower() in ("1", "yes", "y", "true", "on")


def falsy(value):
    return str(value).strip().lower() in ("0", "no", "n", "false", "off", "cancel", "stop", "q", "quit")


def prompt_value(label, current, help_text=""):
    current = "" if current is None else str(current)
    if help_text:
        print(help_text)
    prompt = "{} [{}]: ".format(label, current) if current else "{}: ".format(label)
    try:
        value = input(prompt)
    except EOFError:
        return current
    value = value.strip()
    return value if value else current


def prompt_int(label, current, default):
    while True:
        value = prompt_value(label, current if current not in (None, "") else default)
        try:
            return int(str(value), 0)
        except Exception:
            print("Invalid integer '{}'. Please enter a number such as {}.".format(value, default))
            current = default


def prompt_float(label, current, default):
    while True:
        value = prompt_value(label, current if current not in (None, "") else default)
        try:
            return str(float(str(value)))
        except Exception:
            print("Invalid number '{}'. Please enter a value such as {}.".format(value, default))
            current = default


def apply_interactive_args(args):
    print("")
    print("Functional coverage closure setup")
    print("Press Enter to keep the value shown in brackets.")
    print("")
    if args.analysis_only:
        print("Warning: --analysis-only is set. That mode only checks setup and does not compile, generate/run cases, or rerun regression.")
        answer = prompt_value("Switch to full coverage closure run? y/n", "y")
        if truthy(answer):
            args.analysis_only = False
        else:
            print("Keeping analysis-only mode; no compile/regression will be executed.")
        print("")
    args.sim_dir = prompt_value("0) project sim directory", args.sim_dir or ".", "   Use a VM local sim path for VCS, or HGFS path to auto-relocate.")
    args.model_choice = prompt_value("1) LLM model choice", args.model_choice or "llama", "   Examples: llama, qwen, qwen3.5:9b-q4_K_M")
    args.template_case = prompt_value("2) tc case template file", args.template_case)
    args.cov_path = prompt_value("3) coverage path", args.cov_path)
    args.cases_dir = prompt_value("4) generated tc case directory", args.cases_dir or "cases/auto_llama")
    args.case_list_dir = prompt_value("5) generated tc case lst directory", args.case_list_dir or ".")
    args.case_list = prompt_value("6) generated tc case lst filename", args.case_list or "auto_func_cov_cases.lst")
    args.case_list_format = normalize_case_list_format(prompt_value("7) tc case lst line format", args.case_list_format or "{case}"))
    while not valid_case_list_format(args.case_list_format):
        args.case_list_format = normalize_case_list_format(prompt_value("7) tc case lst line format", "{case}"))
    args.case_in_file = prompt_value("8) fixed .in filename inside each case dir", args.case_in_file)
    args.compile_cmd = prompt_value("9) compile command", args.compile_cmd)
    args.regress_cmd = prompt_value("10) regression command", args.regress_cmd)
    args.max_iterations = prompt_value("11) max closure iterations", args.max_iterations or "3")
    args.max_cross_cases = prompt_value("12) max cases per cross coverpoint", args.max_cross_cases or "0")
    args.target = prompt_value("13) target GROUP coverage percent", args.target or "100")
    args.qwen_timeout = prompt_int("14) LLM timeout seconds", args.qwen_timeout, 60)
    args.urg_cmd = prompt_value("15) URG command", args.urg_cmd or "urg")
    print_ollama_resolution(args)
    print("")
    confirm = prompt_value("Start coverage closure? y/n", "y")
    return truthy(confirm)


def valid_int_text(value, allow_empty=True):
    if value in (None, ""):
        return allow_empty
    try:
        int(str(value), 0)
        return True
    except Exception:
        return False


def valid_float_text(value, allow_empty=True):
    if value in (None, ""):
        return allow_empty
    try:
        float(str(value))
        return True
    except Exception:
        return False


def normalize_numeric_field(args, name, default, is_float=False):
    value = getattr(args, name, "")
    valid = valid_float_text(value, False) if is_float else valid_int_text(value, False)
    if valid:
        return True
    if args.interactive:
        if is_float:
            setattr(args, name, prompt_float("{} value".format(name), value, default))
        else:
            setattr(args, name, str(prompt_int("{} value".format(name), value, default)))
        return True
    print("Invalid {} '{}'; using default {}.".format(name, value, default), file=sys.stderr)
    setattr(args, name, str(default))
    return True


def validate_args(args):
    if args.case_list_format:
        args.case_list_format = normalize_case_list_format(args.case_list_format)
    if args.case_list_format and not valid_case_list_format(args.case_list_format):
        if args.interactive:
            print("Invalid tc case lst line format: {}".format(args.case_list_format))
            args.case_list_format = normalize_case_list_format(prompt_value("tc case lst line format", "{case}"))
            while not valid_case_list_format(args.case_list_format):
                args.case_list_format = normalize_case_list_format(prompt_value("tc case lst line format", "{case}"))
        else:
            print("Invalid tc case lst line format: {}".format(args.case_list_format), file=sys.stderr)
            return False
    normalize_numeric_field(args, "max_iterations", "3")
    normalize_numeric_field(args, "max_cross_cases", "0")
    normalize_numeric_field(args, "target", "100", True)
    if args.regress_cmd and args.case_list and "{case_list}" not in args.regress_cmd:
        print("Warning: regression command does not contain {case_list}; generated lst may not be used.", file=sys.stderr)
        if args.interactive:
            answer = prompt_value("Edit regression command now? y/n", "y")
            if truthy(answer):
                args.regress_cmd = prompt_value("regression command", args.regress_cmd)
    return True


def prepare_project_args(args):
    before = snapshot_args(args)
    if not validate_args(args):
        return ""
    sim_dir = relocate_hgfs_args(args)
    sanitize_project_args(args, sim_dir)
    if not confirm_arg_changes(args, before):
        return ""
    return sim_dir


def build_auto_command(args, qwen_hints):
    if args.auto_script == "__bundled_auto_func_cov__":
        command = [python_command(), os.path.abspath(sys.argv[0]), "--run-auto-func-cov", "close", "--template-case", args.template_case, "--cov-path", args.cov_path, "--dashboard", args.dashboard, "--grpinfo", args.grpinfo, "--urg-cmd", args.urg_cmd, "--target", args.target]
    else:
        command = [python_command(), args.auto_script, "close", "--template-case", args.template_case, "--cov-path", args.cov_path, "--dashboard", args.dashboard, "--grpinfo", args.grpinfo, "--urg-cmd", args.urg_cmd, "--target", args.target]
    if qwen_hints.get("aliases") or qwen_hints.get("constraints"):
        command.extend(["--hints", args.qwen_hints])
    for opt, value in (("--pre-run", args.pre_run), ("--run-case", args.run_case), ("--post-run", args.post_run), ("--compile-cmd", args.compile_cmd), ("--regress-cmd", args.regress_cmd), ("--case-list", args.case_list), ("--case-list-dir", args.case_list_dir), ("--case-list-format", args.case_list_format), ("--case-in-file", args.case_in_file), ("--cases-dir", args.cases_dir), ("--max-iterations", args.max_iterations), ("--max-cross-cases", args.max_cross_cases)):
        if value:
            command.extend([opt, value])
    return " ".join(shell_quote(x) for x in command)


def print_execution_plan(args, sim_dir, command):
    print("")
    print("Pre-run confirmation")
    print("Please review the final values that will be used:")
    generated_dir = expected_generated_cases_dir(args, sim_dir)
    case_root = expected_case_root_for_lst(args, sim_dir)
    rows = [
        ("active sim dir", sim_dir),
        ("model", args.model),
        ("template case", args.template_case),
        ("coverage path", args.cov_path),
        ("input cases_dir", args.cases_dir),
        ("resolved generated case dir", generated_dir),
        ("case root for lst resolution", case_root),
        ("generated case lst directory", args.case_list_dir),
        ("generated case lst filename", args.case_list),
        ("resolved generated case lst", expected_case_list_path(args, sim_dir)),
        ("lst line format", args.case_list_format),
        ("fixed .in filename inside each case dir", args.case_in_file),
        ("compile command", args.compile_cmd),
        ("regression command", args.regress_cmd),
        ("target GROUP coverage", args.target),
        ("max iterations", args.max_iterations),
        ("max cross cases", args.max_cross_cases),
        ("ollama command", args.ollama_bin),
        ("ollama host", args.ollama_host),
        ("ollama models", args.ollama_models),
    ]
    for name, value in rows:
        print("  {}: {}".format(name, value if value else "<empty>"))
    print("  rendered closure command: {}".format(command))
    print("")


def confirm_before_execution(args, sim_dir, command):
    if not args.interactive:
        return "run"
    print_execution_plan(args, sim_dir, command)
    while True:
        answer = prompt_value("Start this execution? y=run, e=edit inputs, n=stop", "y").strip().lower()
        if truthy(answer):
            return "run"
        if answer in ("e", "edit"):
            return "edit"
        if falsy(answer):
            return "stop"
        print("Please enter y, e, or n.")


def find_result_paths(args, sim_dir):
    candidates = [
        ("case list", expected_case_list_path(args, sim_dir)),
        ("generated cases", args.cases_dir),
        ("LLM hints", args.qwen_hints),
        ("case/code map", args.code_map_md),
    ]
    cov_path = resolve_path(sim_dir, args.cov_path)
    if cov_path and str(cov_path).lower() != "auto":
        candidates.extend([
            ("coverage dashboard", os.path.join(cov_path, "urgReport", "dashboard.txt")),
            ("coverage group info", os.path.join(cov_path, "urgReport", "grpinfo.txt")),
        ])
    paths = []
    for label, path in candidates:
        if not path:
            continue
        resolved = resolve_path(sim_dir, path)
        if resolved and os.path.exists(resolved):
            paths.append((label, os.path.relpath(resolved, sim_dir)))
    return paths


def coverage_dashboard_summary(args, sim_dir):
    cov_path = resolve_path(sim_dir, args.cov_path)
    candidates = []
    if args.dashboard and str(args.dashboard).lower() != "auto":
        candidates.append(resolve_path(sim_dir, args.dashboard))
    if cov_path and str(cov_path).lower() != "auto":
        candidates.append(os.path.join(cov_path, "urgReport", "dashboard.txt"))
    candidates.append(resolve_path(sim_dir, "cov/urgReport/dashboard.txt"))
    seen = set()
    for path in candidates:
        if not path or path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            text = read_text(path, 12000)
        except Exception:
            continue
        lines = []
        for raw in text.splitlines():
            line = raw.strip()
            upper = line.upper()
            if ("SCORE" in upper or "GROUP" in upper or "ASSERT" in upper or "LINE" in upper or "COND" in upper or "TOGGLE" in upper) and line:
                lines.append(line)
            if len(lines) >= 8:
                break
        if lines:
            return os.path.relpath(path, sim_dir), lines
    return "", []


def print_post_run_summary(args, sim_dir, rc):
    print("")
    print("Post-run confirmation")
    print("Execution status: {}".format("PASS" if rc == 0 else "FAIL"))
    print("Exit status: {}".format(rc))
    summary_path, summary_lines = coverage_dashboard_summary(args, sim_dir)
    if summary_lines:
        print("Coverage dashboard: {}".format(summary_path))
        for line in summary_lines:
            print("  {}".format(line))
    result_paths = find_result_paths(args, sim_dir)
    if result_paths:
        print("Generated or updated outputs:")
        for label, path in result_paths:
            print("  {}: {}".format(label, path))
    print("")


def confirm_after_success(args, sim_dir):
    if not args.interactive:
        return "finish"
    print_post_run_summary(args, sim_dir, 0)
    while True:
        answer = prompt_value("Confirm the result is correct? y=finish, r=rerun, e=edit inputs and rerun, n=finish with error", "y").strip().lower()
        if truthy(answer):
            return "finish"
        if answer in ("r", "retry", "rerun"):
            return "rerun"
        if answer in ("e", "edit"):
            return "edit"
        if falsy(answer):
            return "error"
        print("Please enter y, r, e, or n.")


def confirm_after_analysis(args, sim_dir):
    if not args.interactive:
        print("Analysis-only mode completed. No compile command, generated-case regression, or coverage closure run was executed.")
        return 0
    decision = confirm_before_execution(args, sim_dir, "analysis-only: no compile/regression command will be executed")
    if decision == "edit":
        edit_repair_args(args)
        sim_dir = prepare_project_args(args)
        if not sim_dir:
            return 1
    elif decision == "stop":
        print("Canceled before analysis-only confirmation.")
        return 1
    print_post_run_summary(args, sim_dir, 0)
    answer = prompt_value("Confirm analysis-only result is correct? y/n", "y")
    return 0 if truthy(answer) else 1


def tail_text(path, max_lines=40):
    try:
        with open(path, "r") as handle:
            lines = handle.readlines()
        return "".join(lines[-max_lines:])
    except Exception:
        return ""


def latest_log_context(sim_dir):
    candidates = []
    for pattern in ("logs/vcs/*.log", "logs/*.log", "cov/urgReport/dashboard.txt", "cov/urgReport/grpinfo.txt"):
        for path in glob.glob(resolve_path(sim_dir, pattern)):
            if os.path.isfile(path):
                candidates.append(path)
    candidates = sorted(candidates, key=lambda p: os.path.getmtime(p), reverse=True)
    parts = []
    for path in candidates[:4]:
        text = tail_text(path, 35)
        if text:
            parts.append("### {}\n{}".format(os.path.relpath(path, sim_dir), text))
    return "\n".join(parts)


def llm_failure_advice(args, sim_dir, return_code):
    if args.skip_qwen:
        return
    if not start_ollama_server(args, sim_dir):
        return
    prompt = [
        "You are helping debug an EDA coverage closure flow. Respond in Chinese with concise, actionable suggestions.",
        "Do not invent files. Focus on correcting user inputs such as template_case, cov_path, cases_dir, case_list_format, compile_cmd, or regress_cmd.",
        "Return plain text, not JSON.",
        "Exit code: {}".format(return_code),
        "Current values:",
        "sim_dir={}".format(sim_dir),
        "template_case={}".format(args.template_case),
        "cov_path={}".format(args.cov_path),
        "cases_dir={}".format(args.cases_dir),
        "case_list_dir={}".format(args.case_list_dir),
        "case_list={}".format(args.case_list),
        "case_list_format={}".format(args.case_list_format),
        "case_in_file={}".format(args.case_in_file),
        "compile_cmd={}".format(args.compile_cmd),
        "regress_cmd={}".format(args.regress_cmd),
        "Recent logs:",
        latest_log_context(sim_dir),
    ]
    try:
        print("")
        print("Local LLM failure analysis:")
        print(ask_ollama(args, "\n".join(prompt)))
    except Exception as exc:
        print("Local LLM failure analysis unavailable: {}".format(exc))


def edit_repair_args(args):
    print("")
    print("Edit the values to retry. Press Enter to keep the current value.")
    args.sim_dir = prompt_value("project sim directory", args.sim_dir)
    args.template_case = prompt_value("tc case template file", args.template_case)
    args.cov_path = prompt_value("coverage path", args.cov_path)
    args.cases_dir = prompt_value("generated tc case directory", args.cases_dir)
    args.case_list_dir = prompt_value("generated tc case lst directory", args.case_list_dir or ".")
    args.case_list = prompt_value("generated tc case lst filename", args.case_list)
    args.case_list_format = normalize_case_list_format(prompt_value("tc case lst line format", args.case_list_format or "{case}"))
    while not valid_case_list_format(args.case_list_format):
        args.case_list_format = normalize_case_list_format(prompt_value("tc case lst line format", "{case}"))
    args.case_in_file = prompt_value("fixed .in filename inside each case dir", args.case_in_file)
    args.compile_cmd = prompt_value("compile command", args.compile_cmd)
    args.regress_cmd = prompt_value("regression command", args.regress_cmd)
    args.max_iterations = prompt_value("max closure iterations", args.max_iterations or "3")
    args.max_cross_cases = prompt_value("max cases per cross coverpoint", args.max_cross_cases or "0")
    args.target = prompt_value("target GROUP coverage percent", args.target or "100")


def repair_after_failure(args, sim_dir, return_code):
    print("")
    print("Coverage closure command failed with exit status {}.".format(return_code))
    print("The Python traceback is suppressed; check the command output above and recent logs under {}.".format(os.path.relpath(resolve_path(sim_dir, "logs"), sim_dir)))
    print("Common fixes: correct the template case path, use a coverage path under the active project, keep {case_list} in the regression command, and match the lst line format to run_lst.")
    llm_failure_advice(args, sim_dir, return_code)
    if not args.interactive:
        return False
    while True:
        answer = prompt_value("Retry? y=retry now, e=edit inputs, n=stop", "e").strip().lower()
        if truthy(answer):
            return True
        if answer in ("e", "edit"):
            edit_repair_args(args)
            return True
        if falsy(answer):
            return False
        print("Please enter y, e, or n.")


def execute_auto_closure(args, qwen_hints, sim_dir):
    attempts = 0
    try:
        attempts = int(str(args.repair_attempts), 0)
    except Exception:
        attempts = 2
    while True:
        rendered = build_auto_command(args, qwen_hints)
        decision = confirm_before_execution(args, sim_dir, rendered)
        if decision == "edit":
            edit_repair_args(args)
            sim_dir = prepare_project_args(args)
            if not sim_dir:
                return 1
            continue
        if decision == "stop":
            print("Canceled before running coverage closure.")
            return 1
        rc = run_shell_status(rendered, sim_dir)
        if rc == 0:
            decision = confirm_after_success(args, sim_dir)
            if decision == "finish":
                return 0
            if decision == "error":
                print("User marked the completed run as incorrect.")
                return 1
            if decision == "edit":
                edit_repair_args(args)
                sim_dir = prepare_project_args(args)
                if not sim_dir:
                    return 1
            continue
        print_post_run_summary(args, sim_dir, rc)
        if attempts <= 0 or not repair_after_failure(args, sim_dir, rc):
            print("Coverage closure stopped after failure. No Python traceback is emitted; fix the inputs above and rerun qwen_cov_close.")
            return rc or 1
        attempts -= 1
        sim_dir = prepare_project_args(args)
        if not sim_dir:
            return rc or 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--run-auto-func-cov":
        return run_auto_func_cov_entry()
    parser = argparse.ArgumentParser(description="Local-LLM assisted wrapper for auto_func_cov.py")
    parser.add_argument("--sim-dir", default=".")
    parser.add_argument("--template-case", default="cases/tc_func_cov_template.in")
    parser.add_argument("--cov-path", default="cov")
    parser.add_argument("--dashboard", default="auto")
    parser.add_argument("--grpinfo", default="auto")
    parser.add_argument("--urg-cmd", default="urg")
    parser.add_argument("--auto-script", default="scripts/auto_func_cov.py")
    parser.add_argument("--filelist", default="vcs.f")
    parser.add_argument("--qwen-hints", default="logs/qwen_cov_hints.json")
    parser.add_argument("--model-choice", default="")
    parser.add_argument("--model", default=os.environ.get("LOCAL_LLM_MODEL", "qwen3.5:9b-q4_K_M"))
    parser.add_argument("--ollama-bin", default=os.environ.get("OLLAMA_BIN", ""))
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", ""))
    parser.add_argument("--ollama-models", default=os.environ.get("OLLAMA_MODELS", ""))
    parser.add_argument("--ollama-log", default="logs/ollama_qwen.log")
    parser.add_argument("--qwen-timeout", type=int, default=60)
    parser.add_argument("--qwen-num-predict", type=int, default=768)
    parser.add_argument("--context-limit", type=int, default=8000)
    parser.add_argument("--skip-qwen", action="store_true")
    parser.add_argument("--analysis-only", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--no-local-relocate", action="store_true")
    parser.add_argument("--extra-context", default="")
    parser.add_argument("--pre-run", default="")
    parser.add_argument("--run-case", default="")
    parser.add_argument("--post-run", default="")
    parser.add_argument("--compile-cmd", default="")
    parser.add_argument("--regress-cmd", default="")
    parser.add_argument("--case-list", default="")
    parser.add_argument("--case-list-dir", default="")
    parser.add_argument("--case-list-format", default="")
    parser.add_argument("--case-in-file", default="")
    parser.add_argument("--cases-dir", default="")
    parser.add_argument("--max-iterations", default="")
    parser.add_argument("--target", default="100")
    parser.add_argument("--max-cross-cases", default="")
    parser.add_argument("--repair-attempts", default="2")
    parser.add_argument("--code-map", default="logs/case_code_map.json")
    parser.add_argument("--code-map-md", default="logs/case_code_map.md")
    parser.add_argument("--code-patch-file", default="logs/llm_code_patch.diff")
    parser.add_argument("--apply-llm-patch", action="store_true")
    args = parser.parse_args()

    apply_bundle_defaults(args)
    if args.interactive and not apply_interactive_args(args):
        print("Canceled by user.")
        return 0
    args.model = resolve_model(args.model_choice, args.model)
    sim_dir = prepare_project_args(args)
    if not sim_dir:
        return 1
    print("Local LLM model selected: {}".format(args.model))

    code_mapping = build_code_mapping(args, sim_dir, {})
    write_code_mapping(args, sim_dir, code_mapping)
    print_code_mapping_summary(code_mapping)

    hints_path = resolve_path(sim_dir, args.qwen_hints)
    qwen_hints = {}
    qwen_response = ""
    if args.skip_qwen:
        print("Qwen skipped; using deterministic coverage closure only.")
    elif start_ollama_server(args, sim_dir):
        try:
            print("Qwen project-adaptation analysis:")
            qwen_response = ask_ollama(args, build_prompt(args, sim_dir, code_mapping))
            print(qwen_response)
            qwen_hints = normalize_hints(extract_json_object(qwen_response))
        except Exception as exc:
            print("Qwen unavailable through Ollama API: {}".format(exc), file=sys.stderr)
    else:
        print("Qwen backend not installed; using deterministic coverage closure only.")

    write_text(hints_path, json.dumps(qwen_hints, indent=2, sort_keys=True) + "\n")
    print("Qwen hints written to {}".format(os.path.relpath(hints_path, sim_dir)))
    print("Qwen hints summary: aliases={} constraints={} notes={}".format(len(qwen_hints.get("aliases", {})), len(qwen_hints.get("constraints", [])), len(qwen_hints.get("notes", []))))
    if qwen_hints:
        code_mapping = build_code_mapping(args, sim_dir, qwen_hints)
        write_code_mapping(args, sim_dir, code_mapping)
        print_code_mapping_summary(code_mapping)
        maybe_apply_llm_code_edit(args, sim_dir, qwen_hints)
    if args.analysis_only:
        return confirm_after_analysis(args, sim_dir)

    return execute_auto_closure(args, qwen_hints, sim_dir)


if __name__ == "__main__":
    sys.exit(main())
