# uncompyle6 version 3.9.3
# Python bytecode version base 3.3 (3230)
# Decompiled from: Python 3.11.5 | packaged by Anaconda, Inc. | (main, Sep 11 2023, 13:26:23) [MSC v.1916 64 bit (AMD64)]
# Embedded file name: scripts/auto_func_cov.py
# Compiled at: 2026-05-06 22:47:40
# Size of source mod 2**32: 52212 bytes
from __future__ import print_function
import argparse, io, json, os, re, subprocess, sys
DEFAULT_DASHBOARD = "auto"
DEFAULT_GRPINFO = "auto"
DEFAULT_COV_PATH = "cov"

def read_text(path):
    with io.open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
        return handle.read()


def resolve_path(base_dir, path):
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def shell_quote(value):
    return "'" + str(value).replace("'", '\'"\'"\'') + "'"


def load_hints(path):
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            data = json.load(handle)
    except Exception as exc:
        print("Ignoring invalid hints file {}: {}".format(path, exc), file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}
    data = sanitize_hints(data)
    return data


def sanitize_hints(hints):
    reserved = set(["case_name", "random_seed", "profile", "frame_count"])
    aliases = hints.get("aliases", {})
    if isinstance(aliases, dict):
        clean_aliases = {}
        for key, value in aliases.items():
            if not not key:
                if not value:
                    continue
                if str(value).strip().lower() in reserved:
                    continue
                clean_aliases[str(key)] = str(value)

        hints["aliases"] = clean_aliases
    return hints


def normalize_hint_name(name):
    name = str(name).strip()
    name = re.sub("[^A-Za-z0-9_$]+", "_", name)
    name = name.strip("_")
    name = name.lower()
    if name.startswith("cp_"):
        name = name[3:]
    return name.lower()


KNOWN_CONFIG_ITEMS = [
 'bnr_space_kernel_r_center', 
 'bnr_space_kernel_g_center', 
 'bnr_space_kernel_b_center', 
 'bnr_color_curve_x_r_first', 
 'bnr_color_curve_x_g_first', 
 'bnr_color_curve_x_b_first', 
 'bnr_color_curve_y_r_first', 
 'bnr_color_curve_y_g_first', 
 'bnr_color_curve_y_b_first', 
 'awb_underexposed_limit', 
 'bnr_space_kernel_r_edge', 
 'bnr_color_curve_x_r_last', 
 'ae_center_illuminance', 
 'awb_overexposed_limit', 
 'gamma_table_r_wdata', 
 'gamma_table_g_wdata', 
 'gamma_table_b_wdata', 
 'luma_kernel_corner', 
 'luma_kernel_center', 
 'ae_target_skewness', 
 'dgain_array_first', 
 'gamma_table_r_addr', 
 'gamma_table_g_addr', 
 'gamma_table_b_addr', 
 'sharpen_strength', 
 'nr2d_weight_first', 
 'rgb_input_enable', 
 'demosaic_enable', 
 'dgain_array_last', 
 'gamma_table_r_wen', 
 'gamma_table_g_wen', 
 'gamma_table_b_wen', 
 'gamma_table_r_ren', 
 'gamma_table_g_ren', 
 'gamma_table_b_ren', 
 'nr2d_weight_last', 
 'nr2d_diff_first', 
 'linear_enable', 
 'stat_ae_enable', 
 'dpc_threshold', 
 'gr_table_wdata', 
 'gb_table_wdata', 
 'nr2d_diff_last', 
 'ae_crop_bottom', 
 'dgain_enable', 
 'gamma_enable', 
 'sharp_enable', 
 'dgain_manual', 
 'csc_standard', 
 'gr_table_addr', 
 'gb_table_addr', 
 'r_table_wdata', 
 'b_table_wdata', 
 'ae_crop_right', 
 'random_seed', 
 'frame_count', 
 'crop_enable', 
 'oecf_enable', 
 'ldci_enable', 
 'nr2d_enable', 
 'gr_table_wen', 
 'gb_table_wen', 
 'gr_table_ren', 
 'gb_table_ren', 
 'r_table_addr', 
 'b_table_addr', 
 'dgain_index', 
 'ae_crop_left', 
 'dpc_enable', 
 'blc_enable', 
 'bnr_enable', 
 'lsc_enable', 
 'ccm_enable', 
 'csc_enable', 
 'awb_enable', 
 'r_table_wen', 
 'b_table_wen', 
 'r_table_ren', 
 'b_table_ren', 
 'ae_crop_top', 
 'awb_frames', 
 'case_name', 
 'wb_enable', 
 'ae_enable', 
 'linear_gr', 
 'linear_gb', 
 'profile', 
 'linear_r', 
 'linear_b', 
 'wb_rgain', 
 'wb_bgain', 
 'blc_gr', 
 'blc_gb', 
 'ccm_rr', 
 'ccm_rg', 
 'ccm_rb', 
 'ccm_gr', 
 'ccm_gg', 
 'ccm_gb', 
 'ccm_br', 
 'ccm_bg', 
 'ccm_bb', 
 'blc_r', 
 'blc_b']

def compact_name(name):
    return re.sub("[^a-z0-9]+", "", str(name).lower())


KNOWN_CONFIG_COMPACT = [(item, compact_name(item)) for item in KNOWN_CONFIG_ITEMS]

def canonical_item_name(name):
    normalized = normalize_hint_name(name)
    compact = compact_name(normalized)
    for item, item_compact in KNOWN_CONFIG_COMPACT:
        if compact == item_compact:
            return item

    for item, item_compact in KNOWN_CONFIG_COMPACT:
        if item_compact and item_compact in compact:
            return item

    return normalized


def hint_alias_map(hints):
    aliases = hints.get("aliases", {}) if hints else {}
    alias_map = {}
    if isinstance(aliases, dict):
        for source, target in aliases.items():
            if not source is None:
                if target is None:
                    continue
                alias_map[str(source)] = str(target)
                alias_map[normalize_hint_name(source)] = str(target)

    elif isinstance(aliases, list):
        for item in aliases:
            if not isinstance(item, dict):
                continue
            source = item.get("source") or item.get("coverpoint") or item.get("signal")
            target = item.get("target") or item.get("item") or item.get("case_item")
            if not source is None:
                if target is None:
                    continue
                alias_map[str(source)] = str(target)
                alias_map[normalize_hint_name(source)] = str(target)

    return alias_map


def hinted_item_name(name, hints):
    if not hints:
        return
    else:
        aliases = hint_alias_map(hints)
        if name in aliases:
            return canonical_item_name(aliases[name])
        else:
            normalized = normalize_hint_name(name)
            value = aliases.get(normalized)
            if value:
                pass
            return canonical_item_name(value)
        return


def mkdir_p(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def report_stamp(dashboard_path, grpinfo_path):
    return max(os.path.getmtime(dashboard_path), os.path.getmtime(grpinfo_path))


def discover_urg_report(search_dir):
    candidates = []
    standard_dashboard = resolve_path(search_dir, "urgReport/dashboard.txt")
    standard_grpinfo = resolve_path(search_dir, "urgReport/grpinfo.txt")
    if os.path.exists(standard_dashboard):
        if os.path.exists(standard_grpinfo):
            candidates.append((report_stamp(standard_dashboard, standard_grpinfo), standard_dashboard, standard_grpinfo))
    for dirpath, dirnames, filenames in os.walk(search_dir):
        dirnames[:] = [d for d in dirnames if d not in ('csrc', 'simv.daidir', '.git')]
        if not "dashboard.txt" not in filenames:
            if "grpinfo.txt" not in filenames:
                continue
            if os.path.basename(dirpath) != "urgReport":
                continue
            dashboard_path = os.path.join(dirpath, "dashboard.txt")
            grpinfo_path = os.path.join(dirpath, "grpinfo.txt")
            candidates.append((report_stamp(dashboard_path, grpinfo_path), dashboard_path, grpinfo_path))

    if not candidates:
        return (None, None)
    else:
        candidates.sort(key=(lambda item: item[0]), reverse=True)
        return (candidates[0][1], candidates[0][2])


def vdb_stamp(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def find_vdb_dirs(cov_path):
    candidates = []
    if os.path.isdir(cov_path) and os.path.basename(cov_path).endswith(".vdb"):
        return [cov_path]
    if not os.path.isdir(cov_path):
        return []
    preferred = os.path.join(cov_path, "simv.vdb")
    if os.path.isdir(preferred):
        candidates.append(preferred)
    for dirpath, dirnames, _ in os.walk(cov_path):
        kept = []
        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            if dirname.endswith(".vdb"):
                candidates.append(full_path)
            elif dirname in ('urgReport', 'csrc', 'simv.daidir', '.git', 'logs', 'waves',
                             'build'):
                continue
            else:
                kept.append(dirname)

        dirnames[:] = kept

    unique = []
    seen = set()
    for path in candidates:
        real = os.path.abspath(path)
        if real not in seen:
            unique.append(real)
            seen.add(real)
            continue

    unique.sort(key=(lambda path: (os.path.basename(path) == "simv.vdb", vdb_stamp(path))), reverse=True)
    return unique


def cov_report_layout(sim_dir, cov_path):
    root = resolve_path(sim_dir, cov_path)
    if os.path.basename(root) == "urgReport":
        return (root, os.path.dirname(root))
    if os.path.basename(root).endswith(".vdb"):
        return (os.path.join(os.path.dirname(root), "urgReport"), root)
    return (
     os.path.join(root, "urgReport"), root)


def generate_urg_report(sim_dir, cov_path, urg_cmd, force=False):
    report_dir, vdb_search_root = cov_report_layout(sim_dir, cov_path)
    dashboard_path = os.path.join(report_dir, "dashboard.txt")
    grpinfo_path = os.path.join(report_dir, "grpinfo.txt")
    if not force and os.path.exists(dashboard_path) and os.path.exists(grpinfo_path):
        return (dashboard_path, grpinfo_path)
    vdb_dirs = find_vdb_dirs(vdb_search_root)
    if not vdb_dirs:
        return (dashboard_path, grpinfo_path)
    mkdir_p(report_dir)
    command = "{} -full64 -dir {} -report {} -format both".format(urg_cmd, shell_quote(vdb_dirs[0]), shell_quote(report_dir))
    run_shell(command, sim_dir)
    return (dashboard_path, grpinfo_path)


def safe_parse_group_variables(sim_dir, dashboard, grpinfo, cov_path, urg_cmd, hints=None):
    try:
        return parse_group_variables(sim_dir, dashboard, grpinfo, cov_path, urg_cmd, hints)
    except Exception as exc:
        print("Unable to parse URG group report; falling back to SV coverpoints: {}".format(exc), file=sys.stderr)
        return []


def report_paths(sim_dir, dashboard, grpinfo, cov_path=None, urg_cmd="urg", build_if_missing=False):
    if dashboard == "auto" and grpinfo == "auto":
        cov_root = resolve_path(sim_dir, cov_path or DEFAULT_COV_PATH)
        found_dashboard, found_grpinfo = discover_urg_report(cov_root)
        if found_dashboard and found_grpinfo:
            return (found_dashboard, found_grpinfo)
        else:
            if build_if_missing:
                return generate_urg_report(sim_dir, cov_path or DEFAULT_COV_PATH, urg_cmd)
            report_dir, _ = cov_report_layout(sim_dir, cov_path or DEFAULT_COV_PATH)
            return (
             os.path.join(report_dir, "dashboard.txt"), os.path.join(report_dir, "grpinfo.txt"))
        return (
         resolve_path(sim_dir, dashboard), resolve_path(sim_dir, grpinfo))


def parse_dashboard(sim_dir, dashboard, grpinfo, cov_path, urg_cmd):
    dashboard_path, _ = report_paths(sim_dir, dashboard, grpinfo, cov_path, urg_cmd, True)
    if not os.path.exists(dashboard_path):
        return {}
    lines = read_text(dashboard_path).splitlines()
    for idx, line in enumerate(lines):
        headers = line.split()
        if not "GROUP" not in headers:
            if "SCORE" not in headers:
                continue
            for value_line in lines[idx + 1:]:
                values = value_line.split()
                if values:
                    return dict(zip(headers, values))

    return {}


def parse_group_variables(sim_dir, dashboard, grpinfo, cov_path, urg_cmd, hints=None):
    _, grpinfo_path = report_paths(sim_dir, dashboard, grpinfo, cov_path, urg_cmd, True)
    if not os.path.exists(grpinfo_path):
        return []
    else:
        variables = []
        by_name = {}
        cross_names = set(parse_cross_item_map(sim_dir, hints).keys())
        pattern = re.compile("^([A-Za-z_][A-Za-z0-9_$]*)\\s+(\\d+)\\s+(\\d+)\\s+(\\d+)\\s+([0-9.]+)")
        table_kind = None
        for line in read_text(grpinfo_path).splitlines():
            words = line.split()
            if not table_kind:
                if words[:5] == ['VARIABLE', 'EXPECTED', 'UNCOVERED', 'COVERED', 'PERCENT']:
                    table_kind = "variable"
                elif words[:5] == ['CROSS', 'EXPECTED', 'UNCOVERED', 'COVERED', 'PERCENT']:
                    table_kind = "cross"
                continue
            if line.startswith("----"):
                table_kind = None
                continue
            match = pattern.match(line)
            if not match:
                continue
            name, expected, uncovered, covered, percent = match.groups()
            kind = "cross" if name in cross_names else table_kind
            entry = {"name": name, 
             "item": (hinted_item_name(name, hints) or canonical_item_name(coverpoint_to_item(name))), 
             "kind": kind, 
             "expected": (int(expected)), 
             "uncovered": (int(uncovered)), 
             "covered": (int(covered)), 
             "percent": (float(percent))}
            if name not in by_name:
                variables.append(entry)
                by_name[name] = entry
            else:
                old = by_name[name]
                old["expected"] = max(old["expected"], entry["expected"])
                old["uncovered"] = max(old["uncovered"], entry["uncovered"])
                old["covered"] = max(old["covered"], entry["covered"])
                old["percent"] = min(old["percent"], entry["percent"])

        return variables


def is_variable_entry(var):
    return var.get("kind", "variable") == "variable"


def is_cross_entry(var):
    return var.get("kind", "variable") == "cross"


def coverpoint_to_item(name):
    normalized = normalize_hint_name(name)
    if normalized.startswith("cp_"):
        return normalized[3:]
    return normalized


def print_status(sim_dir, dashboard, grpinfo, cov_path, urg_cmd, limit):
    try:
        summary = parse_dashboard(sim_dir, dashboard, grpinfo, cov_path, urg_cmd)
        variables = parse_group_variables(sim_dir, dashboard, grpinfo, cov_path, urg_cmd)
    except Exception as exc:
        print("No usable URG report found: {}".format(exc))
        return

    dashboard_path, _ = report_paths(sim_dir, dashboard, grpinfo, cov_path, urg_cmd, True)
    if not summary:
        print("No URG dashboard found at {}".format(dashboard_path))
        return
    else:
        try:
            group = float(summary.get("GROUP", "nan"))
        except ValueError:
            group = None

        print("Coverage summary: SCORE={} LINE={} COND={} TOGGLE={} FSM={} BRANCH={} GROUP={}".format(summary.get("SCORE", "--"), summary.get("LINE", "--"), summary.get("COND", "--"), summary.get("TOGGLE", "--"), summary.get("FSM", "--"), summary.get("BRANCH", "--"), summary.get("GROUP", "--")))
        if variables:
            missing = [v for v in variables if v["percent"] < 100.0]
            variable_count = len([v for v in variables if is_variable_entry(v)])
            cross_count = len([v for v in variables if is_cross_entry(v)])
            print("Functional coverpoints: total={} variables={} crosses={} full={} missing={}".format(len(variables), variable_count, cross_count, len(variables) - len(missing), len(missing)))
            for var in missing[:limit]:
                print("  {}: {}% covered={}/{} uncovered={}".format(var["name"], var["percent"], var["covered"], var["expected"], var["uncovered"]))

            if len(missing) > limit:
                print("  ... {} more coverpoints below 100%".format(len(missing) - limit))
        return group


def strip_comment(line):
    pos = line.find("#")
    if pos >= 0:
        return line[:pos]
    return line


def parse_case_template(path):
    entries = []
    with io.open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
        for raw_line in handle:
            body = strip_comment(raw_line).strip()
            if not body:
                continue
            parts = body.split()
            if len(parts) < 3:
                continue
            entries.append({"name": (parts[0]), 
             "random_flag": (parts[1]), 
             "value": (parts[2]), 
             "raw": (raw_line.rstrip("\n"))})

    return entries


def parse_int(value, default=0):
    try:
        return int(str(value), 0)
    except ValueError:
        return default


def sv_int(value):
    value = str(value).strip()
    match = re.match("(-?)(\\d+)'[sS]?[dD]([0-9_]+)$", value)
    if match:
        sign, _, digits = match.groups()
        parsed = int(digits.replace("_", ""), 10)
        if sign:
            return -parsed
        return parsed
    return int(value.replace("_", ""), 0)


def safe_eval(expr, constants):
    expr = str(expr).strip()
    for name, value in constants.items():
        expr = re.sub("\\b{}\\b".format(re.escape(name)), str(value), expr)

    expr = re.sub("(\\d+)'[sS]?[dD]([0-9_]+)", (lambda m: m.group(2).replace("_", "")), expr)
    if not re.match("^[0-9_+\\-*/%() \\t]+$", expr):
        raise ValueError("unsupported expression '{}'".format(expr))
    return int(eval(expr, {"__builtins__": None}, {}))


def representative_value(low, high, prefer_high):
    if low > high:
        low, high = high, low
    if low == high:
        return low
    if prefer_high:
        return high
    candidates = [0, 1, -1, 2, 3, 4, 8, 16, 23, 28, 32, 64, 128, 224, 256, 
     512, 
     768, 900, 1023, 1024, 2048, 3500, 4095, 12000, 32768, 
     60000, 
     65535, 262144, 524288, 900000, 1048575, -2048, 
     -1024, 
     -512, -16]
    for candidate in candidates:
        if low <= candidate <= high:
            return candidate

    return low


def parse_constants(text):
    constants = {}
    pattern = re.compile("\\b(?:localparam|parameter)\\b\\s+(?:\\w+\\s+)*(\\w+)\\s*=\\s*([^;]+);")
    for name, expr in pattern.findall(text):
        try:
            constants[name] = safe_eval(expr, constants)
        except Exception:
            pass

    return constants


def parse_bin_values(bin_body, constants, prefer_high, expand_ranges):
    values = []
    for low_expr, high_expr in re.findall("\\[\\s*([^:\\]]+)\\s*:\\s*([^\\]]+)\\s*\\]", bin_body):
        try:
            low = safe_eval(low_expr, constants)
            high = safe_eval(high_expr, constants)
            if expand_ranges and high >= low and high - low <= 64:
                values.extend(list(range(low, high + 1)))
            else:
                values.append(representative_value(low, high, prefer_high))
        except Exception:
            pass

    body_without_ranges = re.sub("\\[[^\\]]+\\]", "", bin_body)
    for token in body_without_ranges.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(safe_eval(token, constants))
        except Exception:
            pass

    return values


def discover_sv_files(sim_dir):
    search_roots = [
     sim_dir]
    files = []
    for root in search_roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ('build', 'logs', 'cov',
                                                            'waves', 'csrc')]
            for filename in filenames:
                if filename.endswith(('.sv', '.v')):
                    files.append(os.path.join(dirpath, filename))
                    continue

    return files


def parse_coverpoint_value_map(sim_dir, hints=None):
    value_map = {}
    cp_start = re.compile("\\b(cp_\\S+|\\w+)\\s*:\\s*coverpoint\\b")
    bin_pattern = re.compile("\\bbins\\s+\\w+(\\[\\])?\\s*=\\s*\\{([^;]+)\\};")
    for path in discover_sv_files(sim_dir):
        try:
            text = read_text(path)
        except Exception:
            continue

        constants = parse_constants(text)
        lines = text.splitlines()
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            match = cp_start.search(line)
            if not match:
                idx += 1
                continue
            cp_name = match.group(1)
            block_lines = [line]
            balance = line.count("{") - line.count("}")
            while balance > 0 and idx + 1 < len(lines):
                idx += 1
                block_lines.append(lines[idx])
                balance += lines[idx].count("{") - lines[idx].count("}")

            block = "\n".join(block_lines)
            item = hinted_item_name(cp_name, hints) or canonical_item_name(coverpoint_to_item(cp_name))
            prefer_high = "over" in item.lower()
            values = []
            for array_suffix, bin_body in bin_pattern.findall(block):
                for value in parse_bin_values(bin_body, constants, prefer_high, array_suffix == "[]"):
                    if value not in values:
                        values.append(value)
                        continue

            if values:
                value_map[item] = values
            idx += 1

    return value_map


def strip_sv_line_comment(line):
    pos = line.find("//")
    if pos >= 0:
        return line[:pos]
    return line


def parse_cross_item_map(sim_dir, hints=None):
    cross_map = {}
    cp_name_to_item = {}
    cp_start = re.compile("\\b(cp_\\S+|\\w+)\\s*:\\s*coverpoint\\b")
    cross_start = re.compile("\\b(\\w+)\\s*:\\s*cross\\s+([^;{]+)")
    for path in discover_sv_files(sim_dir):
        try:
            lines = read_text(path).splitlines()
        except Exception:
            continue

        for raw_line in lines:
            line = strip_sv_line_comment(raw_line)
            cp_match = cp_start.search(line)
            if cp_match:
                cp_name = cp_match.group(1).strip()
                cp_name_to_item[cp_name] = hinted_item_name(cp_name, hints) or canonical_item_name(coverpoint_to_item(cp_name))
                continue

        for raw_line in lines:
            line = strip_sv_line_comment(raw_line)
            cross_match = cross_start.search(line)
            if not cross_match:
                continue
            cross_name, body = cross_match.groups()
            refs = []
            for token in body.split(","):
                token = token.strip()
                token = re.sub("\\s+.*$", "", token)
                token = token.strip()
                if token:
                    refs.append(token)
                    continue

            items = []
            for ref in refs:
                item = cp_name_to_item.get(ref, hinted_item_name(ref, hints) or canonical_item_name(coverpoint_to_item(ref)))
                if item not in items:
                    items.append(item)
                    continue

            if len(items) >= 2:
                cross_map[cross_name] = items
                continue

    return cross_map


def cover_vars_from_sv(sim_dir, hints=None):
    value_map = parse_coverpoint_value_map(sim_dir, hints)
    variables = []
    for item in sorted(value_map):
        variables.append({"name": ("cp_" + item), 
         "item": item, 
         "kind": "variable", 
         "expected": (len(value_map[item])), 
         "uncovered": (len(value_map[item])), 
         "covered": 0, 
         "percent": 0.0})

    return variables


def values_for_expected_count(count):
    if count <= 1:
        return [0]
    else:
        if count == 2:
            return [0, 1]
        if count == 3:
            return [0, 1, 2]
        if count == 4:
            pass
        return [
         0, 1, 2, 3]
    return [
     0, 1, 2, 3, 4]


def normalize_values(values, expected_count):
    if not values:
        return values_for_expected_count(expected_count)
    if expected_count > 0 and len(values) > expected_count:
        return values[:expected_count]
    return values


def rotated_values(values, offset):
    if len(values) <= 2:
        return values
    offset = offset % len(values)
    return values[offset:] + values[:offset]


def cartesian_product(value_lists, max_count):
    combos = [[]]
    for values in value_lists:
        next_combos = []
        for combo in combos:
            for value in values:
                next_combos.append(combo + [value])
                if max_count and len(next_combos) >= max_count:
                    break

            if max_count and len(next_combos) >= max_count:
                break

        combos = next_combos
        if max_count and len(combos) >= max_count:
            break

    return combos


def hint_constraints(hints):
    constraints = hints.get("constraints", []) if hints else []
    if isinstance(constraints, list):
        return constraints
    return []


def compare_constraint(lhs, op, rhs):
    if op in ('<', 'lt'):
        return lhs < rhs
    else:
        if op in ('<=', 'le'):
            return lhs <= rhs
        else:
            if op in ('>', 'gt'):
                return lhs > rhs
            if op in ('>=', 'ge'):
                return lhs >= rhs
            if op in ('==', '=', 'eq'):
                pass
            return lhs == rhs
        if op in ('!=', 'ne'):
            pass
        return lhs != rhs
    return True


def constraint_value(value, values):
    key = normalize_hint_name(value)
    if key in values:
        return (values[key], True)
    try:
        return (
         int(value, 0), True)
    except Exception:
        return (
         value, False)


def combo_is_legal(items, combo, hints=None):
    values = {}
    for idx, item in enumerate(items):
        try:
            values[item.lower()] = int(combo[idx])
        except Exception:
            values[item.lower()] = combo[idx]

    for name, value in values.items():
        if "under" not in name:
            continue
        peer = name.replace("under", "over")
        if peer in values and value >= values[peer]:
            return False

    for name, value in values.items():
        if "left" in name:
            peer = name.replace("left", "right")
            if peer in values and value > values[peer]:
                return False
        if "top" in name:
            peer = name.replace("top", "bottom")
            if peer in values and value > values[peer]:
                return False
            continue

    for constraint in hint_constraints(hints):
        if not isinstance(constraint, dict):
            continue
        lhs_name = constraint.get("lhs") or constraint.get("left") or constraint.get("item")
        rhs_name = constraint.get("rhs") or constraint.get("right") or constraint.get("peer")
        op = constraint.get("op") or constraint.get("operator")
        if not not lhs_name:
            if not not rhs_name:
                if not op:
                    continue
                lhs_key = normalize_hint_name(lhs_name)
                if lhs_key not in values:
                    continue
                lhs_value = values[lhs_key]
                rhs_value, _ = constraint_value(rhs_name, values)
                try:
                    lhs_value = int(lhs_value)
                except Exception:
                    pass

                if not compare_constraint(lhs_value, op, rhs_value):
                    return False

    return True


def legal_cartesian_product(items, value_lists, max_count, hints=None):
    combos = []
    for combo in cartesian_product(value_lists, 0):
        if not combo_is_legal(items, combo, hints):
            continue
        combos.append(combo)
        if max_count and len(combos) >= max_count:
            break

    return combos


def align_plan_lengths(plan, keys):
    lengths = [len(plan.get(key, [])) for key in keys]
    target = max(lengths or [0])
    if target <= 0:
        return
    for key in keys:
        values = plan.setdefault(key, [])
        if not values:
            values.append(0)
        while len(values) < target:
            values.append(values[-1])


def append_cross_combos(plan, matched_set, cross_vars, cross_item_map, value_map, max_cross_cases, hints=None, item_key_map=None):
    cross_matched = []
    cross_unmatched = []
    locked_items = set()
    for var in cross_vars:
        cross_name = var["name"]
        items = cross_item_map.get(cross_name, [])
        if not items:
            cross_unmatched.append(cross_name)
            continue
        usable_items = []
        value_lists = []
        missing_item = False
        for item in items:
            if item not in matched_set:
                missing_item = True
                break
            values = normalize_values(value_map.get(item, []), 0)
            if not values:
                missing_item = True
                break
            usable_items.append(item)
            value_lists.append(values)

        if missing_item or len(usable_items) < 2:
            cross_unmatched.append(cross_name)
            continue
        limit = max_cross_cases
        combos = legal_cartesian_product(usable_items, value_lists, limit, hints)
        if not combos:
            cross_unmatched.append(cross_name)
            continue
        plan_keys = [item_key_map.get(item, item) if item_key_map else item for item in usable_items]
        align_plan_lengths(plan, plan_keys)
        for combo in combos:
            for idx, item in enumerate(usable_items):
                plan_key = item_key_map.get(item, item) if item_key_map else item
                plan.setdefault(plan_key, []).append(combo[idx])
                locked_items.add(plan_key)

        cross_matched.append(cross_name)

    return (
     cross_matched, cross_unmatched, locked_items)


def deconflict_pairs(plan, locked_items=None):
    locked_items = locked_items or set()
    keys = list(plan.keys())
    handled = set()

    def as_int(value):
        try:
            return (int(value), True)
        except Exception:
            return (
             value, False)

    def unique_sorted_numeric(values):
        seen = set()
        numeric = []
        for value in values:
            number, ok = as_int(value)
            if not not ok:
                if number in seen:
                    continue
                seen.add(number)
                numeric.append(number)

        return sorted(numeric)

    def build_ordered_pair_schedule(lhs_values, rhs_values, relation):
        lhs_numeric = unique_sorted_numeric(lhs_values)
        rhs_numeric = unique_sorted_numeric(rhs_values)
        if not lhs_numeric or not rhs_numeric:
            return None
        else:
            pairs = []

            def is_legal(lhs, rhs):
                if relation == "lt":
                    return lhs < rhs
                return lhs <= rhs

            def add_pair(lhs, rhs):
                if is_legal(lhs, rhs):
                    if (lhs, rhs) not in pairs:
                        pairs.append((lhs, rhs))

            for lhs in lhs_numeric:
                legal_rhs = [rhs for rhs in rhs_numeric if is_legal(lhs, rhs)]
                if legal_rhs:
                    add_pair(lhs, legal_rhs[0])
                    continue

            for rhs in rhs_numeric:
                legal_lhs = [lhs for lhs in lhs_numeric if is_legal(lhs, rhs)]
                if legal_lhs:
                    add_pair(legal_lhs[-1], rhs)
                    continue

            if not pairs:
                return None
            return ([lhs for lhs, _ in pairs], [rhs for _, rhs in pairs])

    def build_spatial_pair_schedule(lhs_values, rhs_values):
        lhs_numeric = unique_sorted_numeric(lhs_values)
        rhs_numeric = unique_sorted_numeric(rhs_values)
        if not lhs_numeric or not rhs_numeric:
            return None
        else:
            min_lhs = lhs_numeric[0]
            min_rhs = rhs_numeric[0]
            pairs = []

            def add_pair(lhs, rhs):
                if (
                 lhs, rhs) not in pairs:
                    pairs.append((lhs, rhs))

            for lhs in lhs_numeric:
                add_pair(lhs, min_rhs)

            for rhs in rhs_numeric:
                add_pair(min_lhs, rhs)

            return ([lhs for lhs, _ in pairs], [rhs for _, rhs in pairs])

    for left_word, right_word in [('left', 'right'), ('top', 'bottom')]:
        for key in keys:
            key_lower = key.lower()
            if not left_word not in key_lower:
                if not key in handled:
                    if key in locked_items:
                        continue
                    peer = None
                    for candidate in keys:
                        if candidate != key and candidate not in locked_items and candidate.lower() == key_lower.replace(left_word, right_word):
                            peer = candidate
                            break

                    if not peer:
                        continue
                    values = list(plan[key])
                    peer_values = list(plan[peer])
                    if not len(values) < 4:
                        if len(peer_values) < 4:
                            continue
                        schedule = build_spatial_pair_schedule(values, peer_values)
                        if not schedule:
                            continue
                        plan[key], plan[peer] = schedule
                        handled.add(key)
                        handled.add(peer)

    for key in keys:
        key_lower = key.lower()
        if not "under" not in key_lower:
            if key in locked_items:
                continue
            peer = None
            for candidate in keys:
                if candidate != key and candidate not in locked_items and candidate.lower() == key_lower.replace("under", "over"):
                    peer = candidate
                    break

            if not peer:
                continue
            values = list(plan[key])
            peer_values = list(plan[peer])
            if not not values:
                if not peer_values:
                    continue
                schedule = build_ordered_pair_schedule(values, peer_values, "lt")
                if schedule:
                    plan[key], plan[peer] = schedule
                continue

    return plan


def build_value_plan(template_entries, cover_vars, sv_value_map, cross_item_map, max_cross_cases, hints=None):
    cover_by_item = {}
    for var in cover_vars:
        if is_variable_entry(var):
            cover_by_item[canonical_item_name(var["item"])] = var
            continue

    plan = {}
    matched = []
    matched_canonical = []
    unmatched_template = []
    template_to_canonical = {}
    canonical_to_template = {}
    for entry in template_entries:
        item = entry["name"]
        canonical = canonical_item_name(item)
        template_to_canonical[item] = canonical
        if canonical in cover_by_item:
            var = cover_by_item[canonical]
            values = normalize_values(sv_value_map.get(canonical, []), var["expected"])
            plan[item] = rotated_values(values, len(matched))
            matched.append(item)
            matched_canonical.append(canonical)
            canonical_to_template[canonical] = item
        else:
            unmatched_template.append(item)

    matched_set = set(matched_canonical)
    cross_vars = [var for var in cover_vars if is_cross_entry(var) and var["percent"] < 100.0]
    cross_matched, cross_unmatched, cross_locked_items = append_cross_combos(plan, matched_set, cross_vars, cross_item_map, sv_value_map, max_cross_cases, hints, canonical_to_template)
    unmatched_cover = sorted([item for item in cover_by_item if item not in matched_set])
    plan = deconflict_pairs(plan, cross_locked_items)
    return (plan, matched, unmatched_template, unmatched_cover, cross_matched, cross_unmatched)


def case_name(prefix, index):
    return "{}{:02d}".format(prefix, index)


def format_case_line(item, random_flag, value):
    return "{:<30} {:<12} {}".format(item, random_flag, value)


def case_record_paths(sim_dir, cases_dir, name, case_in_file=""):
    if case_in_file:
        rel_dir = os.path.join(cases_dir, name)
        rel_file = os.path.join(rel_dir, case_in_file)
    else:
        rel_file = os.path.join(cases_dir, "{}.in".format(name))
        rel_dir = os.path.dirname(rel_file)
    rel_file_no_ext = os.path.splitext(rel_file)[0]
    abs_file = resolve_path(sim_dir, rel_file)
    abs_dir = resolve_path(sim_dir, rel_dir)
    return {
        "case_dir": rel_dir,
        "case_dir_abs": abs_dir,
        "case_file": rel_file,
        "case_file_no_ext": rel_file_no_ext,
        "case_file_abs": abs_file,
        "case_file_abs_no_ext": os.path.splitext(abs_file)[0],
        "case_file_basename": os.path.basename(rel_file),
        "case_file_basename_no_ext": os.path.splitext(os.path.basename(rel_file))[0],
    }


def case_records(sim_dir, cases_dir, names, case_in_file=""):
    records = []
    for idx, name in enumerate(names):
        paths = case_record_paths(sim_dir, cases_dir, name, case_in_file)
        record = {"index": idx, 
         "index1": (idx + 1), 
         "case": name, 
         "case_in_file": case_in_file,
         "cases_dir": cases_dir, 
         "cases_dir_abs": (resolve_path(sim_dir, cases_dir))}
        record.update(paths)
        records.append(record)

    return records


def case_list_format_from_hints(hints):
    if not hints:
        return ""
    for key in ('case_list_format', 'lst_format', 'case_lst_format'):
        value = hints.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    case_list = hints.get("case_list")
    if isinstance(case_list, dict):
        for key in ('format', 'line_format', 'lst_format'):
            value = case_list.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                joined = " ".join(str(item) for item in value if str(item).strip())
                if joined.strip():
                    return joined.strip()
                continue

    return ""


def resolve_case_list_format(cli_format, hints, case_in_file=""):
    if cli_format and cli_format.strip() and cli_format.strip().lower() != "auto":
        value = normalize_case_list_format(cli_format.strip())
        if not valid_case_list_format(value):
            raise ValueError("Invalid --case-list-format '{}'. Use a format placeholder such as {{case_file}}, {{case_file_no_ext}}, {{case}}, or '{{case}} {{case_file}}'.".format(value))
        return value
    hinted = case_list_format_from_hints(hints)
    if hinted:
        hinted = normalize_case_list_format(hinted)
        if valid_case_list_format(hinted):
            return hinted
    return "{case}" if case_in_file else "{case_file}"


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
    allowed = ['{case}', 
     '{case_file}', 
     '{case_file_no_ext}', 
     '{case_file_rel}', 
     '{case_file_rel_no_ext}', 
     '{case_file_abs}', 
     '{case_file_abs_no_ext}', 
     '{case_file_basename}', 
     '{case_file_basename_no_ext}', 
     '{cases_dir}', 
     '{cases_dir_abs}', 
     '{case_dir}', 
     '{case_dir_abs}', 
     '{case_in_file}', 
     '{index}', 
     '{index1}']
    return any(token in value for token in allowed)


def infer_cases_dir_from_case_list_format(line_format):
    for token in str(line_format).strip().split():
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


def path_is_under(path, root):
    path = os.path.abspath(path)
    root = os.path.abspath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def relpath_if_under(path, root):
    path = os.path.abspath(path)
    root = os.path.abspath(root)
    if path_is_under(path, root):
        return os.path.relpath(path, root)
    return path


def template_case_root(sim_dir, template_case):
    root = os.path.dirname(os.path.abspath(template_case))
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


def effective_cases_dir(cases_dir, line_format, sim_dir, template_case):
    inferred = infer_cases_dir_from_case_list_format(line_format)
    base_dir = cases_dir or template_case_root(sim_dir, template_case) or "cases"
    if inferred:
        selected = join_cases_dir_and_lst_parent(base_dir, inferred)
        print("Generated case directory resolved from input cases_dir '{}' and lst path '{}': {}".format(base_dir, inferred, selected))
        return selected
    return base_dir


def effective_case_root_for_lst(sim_dir, template_case, generated_cases_dir, line_format):
    inferred = infer_cases_dir_from_case_list_format(line_format)
    if inferred:
        stripped = strip_component_suffix(generated_cases_dir, inferred)
        if stripped:
            return stripped.replace("\\", "/")
        return template_case_root(sim_dir, template_case) or "."
    if line_format_uses_bare_case(line_format):
        return generated_cases_dir
    return case_root_from_cases_dir(sim_dir, template_case, generated_cases_dir)


def render_case_list_line(line_format, record):
    context = dict(record)
    context["case_file_rel"] = record["case_file"]
    context["case_file_rel_no_ext"] = record["case_file_no_ext"]
    return line_format.format(**context)


def effective_case_list_path(sim_dir, case_list_dir, case_list):
    if not case_list:
        return ""
    if os.path.isabs(case_list):
        return case_list
    normalized = str(case_list).replace("\\", "/")
    if case_list_dir and "/" not in normalized and "\\" not in str(case_list):
        return resolve_path(sim_dir, os.path.join(case_list_dir, case_list))
    return resolve_path(sim_dir, case_list)


def write_case_list(sim_dir, cases_dir, names, case_list, line_format, case_list_dir="", case_in_file=""):
    if not case_list:
        return ""
    records = case_records(sim_dir, cases_dir, names, case_in_file)
    list_path = effective_case_list_path(sim_dir, case_list_dir, case_list)
    parent = os.path.dirname(list_path)
    if parent:
        if not os.path.isdir(parent):
            os.makedirs(parent)
    lines = [render_case_list_line(line_format, record) for record in records]
    with io.open(list_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + ("\n" if lines else ""))
    print("Generated tc case list {} with format '{}'".format(list_path, line_format))
    return list_path


def write_cases(sim_dir, template_case, cover_vars, prefix, cases_dir, max_cross_cases, hints=None, case_in_file=""):
    template_entries = parse_case_template(template_case)
    sv_value_map = parse_coverpoint_value_map(sim_dir, hints)
    cross_item_map = parse_cross_item_map(sim_dir, hints)
    plan, matched, unmatched_template, unmatched_cover, cross_matched, cross_unmatched = build_value_plan(template_entries, cover_vars, sv_value_map, cross_item_map, max_cross_cases, hints)
    phase_count = max([len(values) for values in plan.values()] or [1])
    output_dir = resolve_path(sim_dir, cases_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    names = []
    for idx in range(phase_count):
        name = case_name(prefix, idx)
        names.append(name)
        lines = [
         "# Auto-generated by scripts/auto_func_cov.py from {}.".format(os.path.basename(template_case)),
         "# item_name                  random_flag  value_or_range"]
        for entry in template_entries:
            item = entry["name"]
            canonical = canonical_item_name(item)
            random_flag = entry["random_flag"]
            value = entry["value"]
            if canonical == "case_name":
                value = name
            elif canonical == "random_seed":
                value = 9100 + idx
            elif item in plan:
                values = plan[item]
                value = values[idx] if idx < len(values) else values[-1]
                random_flag = "0"
            lines.append(format_case_line(item, random_flag, value))

        if case_in_file:
            case_dir = os.path.join(output_dir, name)
            if not os.path.isdir(case_dir):
                os.makedirs(case_dir)
            path = os.path.join(case_dir, case_in_file)
        else:
            path = os.path.join(output_dir, "{}.in".format(name))
        with io.open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    print("Generated {} functional coverage closure cases under {}".format(len(names), output_dir))
    print("Template entries matched to coverpoints: {}".format(len(matched)))
    if cross_matched:
        print("Cross coverpoints scheduled: {}".format(len(cross_matched)))
    if cross_unmatched:
        print("Cross coverpoints not schedulable from template items: {}".format(len(cross_unmatched)))
        for item in cross_unmatched[:20]:
            print("  {}".format(item))

        if len(cross_unmatched) > 20:
            print("  ... {} more".format(len(cross_unmatched) - 20))
    if unmatched_cover:
        print("Coverpoints without same-name template items: {}".format(len(unmatched_cover)))
        for item in unmatched_cover[:20]:
            print("  {}".format(item))

        if len(unmatched_cover) > 20:
            print("  ... {} more".format(len(unmatched_cover) - 20))
    for name in names:
        paths = case_record_paths(sim_dir, cases_dir, name, case_in_file)
        print("  {}".format(os.path.relpath(resolve_path(sim_dir, paths["case_file"]), sim_dir)))

    return names


def render_command(template, sim_dir, case_name_value, case_file_value, cov_dir_value, urg_report_value, case_list_value="", cases_dir_value="", case_in_file_value=""):
    case_file_abs = resolve_path(sim_dir, case_file_value) if case_file_value else ""
    case_list_abs = resolve_path(sim_dir, case_list_value) if case_list_value else ""
    cases_dir_abs = resolve_path(sim_dir, cases_dir_value) if cases_dir_value else ""
    case_dir_value = os.path.dirname(case_file_value) if case_file_value else ""
    case_dir_abs = resolve_path(sim_dir, case_dir_value) if case_dir_value else ""
    context = {"sim_dir": sim_dir, 
     "case": case_name_value, 
     "case_file": case_file_value, 
     "case_file_abs": case_file_abs, 
     "case_dir": case_dir_value, 
     "case_dir_abs": case_dir_abs, 
     "case_in_file": case_in_file_value,
     "cov_dir": cov_dir_value, 
     "urg_report": urg_report_value, 
     "case_list": case_list_value, 
     "case_list_abs": case_list_abs, 
     "cases_dir": cases_dir_value, 
     "cases_dir_abs": cases_dir_abs}
    return template.format(**context)


def case_root_from_cases_dir(sim_dir, template_case, cases_dir):
    template_root = os.path.dirname(os.path.abspath(template_case))
    cases_abs = resolve_path(sim_dir, cases_dir)
    if path_is_under(cases_abs, template_root):
        return relpath_if_under(template_root, sim_dir).replace("\\", "/")
    return relpath_if_under(os.path.dirname(cases_abs), sim_dir).replace("\\", "/")


def run_shell(command, cwd):
    print("$ " + command)
    subprocess.check_call(command, shell=True, cwd=cwd)


def run_commands(commands, sim_dir, case_name_value, case_file_value, cov_dir_value, urg_report_value, case_list_value="", cases_dir_value="", case_in_file_value=""):
    for command in commands:
        run_shell(render_command(command, sim_dir, case_name_value or "", case_file_value or "", cov_dir_value, urg_report_value, case_list_value or "", cases_dir_value or "", case_in_file_value or ""), sim_dir)


def single_command(text):
    if not text or not text.strip():
        return []
    return [
     text.strip()]


def split_commands(text):
    if not text:
        return []
    return [cmd.strip() for cmd in text.split(";") if cmd.strip()]


def template_case_name(template_case):
    return os.path.splitext(os.path.basename(template_case))[0]


def command_cov_paths(sim_dir, cov_path):
    report_dir, vdb_search_root = cov_report_layout(sim_dir, cov_path)
    if os.path.basename(vdb_search_root).endswith(".vdb"):
        cov_dir = os.path.relpath(vdb_search_root, sim_dir)
    else:
        cov_dir = os.path.relpath(os.path.join(vdb_search_root, "simv.vdb"), sim_dir)
    return (
     cov_dir, os.path.relpath(report_dir, sim_dir))


def run_template_index(args, sim_dir, template_case, hints):
    print("Building functional coverage index from template case:")
    cov_dir, urg_report = command_cov_paths(sim_dir, args.cov_path)
    run_commands(split_commands(args.pre_run), sim_dir, "", "", cov_dir, urg_report)
    run_commands(split_commands(args.run_case), sim_dir, template_case_name(template_case), os.path.relpath(template_case, sim_dir), cov_dir, urg_report)
    run_commands(split_commands(args.post_run), sim_dir, "", "", cov_dir, urg_report)
    if not split_commands(args.post_run):
        generate_urg_report(sim_dir, args.cov_path, args.urg_cmd, True)
    return parse_group_variables(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, hints)


def run_closure(args, sim_dir, template_case, cover_vars, hints):
    if single_command(args.regress_cmd):
        return run_closure_with_regress_cmd(args, sim_dir, template_case, cover_vars, hints)
    else:
        print("Current coverage before adjustment:")
        print_status(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, args.status_limit)
        cover_vars = run_template_index(args, sim_dir, template_case, hints)
        if not cover_vars:
            print("No functional coverpoints were found after running the template case.", file=sys.stderr)
            return 1
        else:
            cases = write_cases(sim_dir, template_case, cover_vars, args.prefix, args.cases_dir, args.max_cross_cases, hints, args.case_in_file)
            cov_dir, urg_report = command_cov_paths(sim_dir, args.cov_path)
            for name in cases:
                case_file = case_record_paths(sim_dir, args.cases_dir, name, args.case_in_file)["case_file"]
                run_commands(split_commands(args.run_case), sim_dir, name, case_file, cov_dir, urg_report, "", args.cases_dir, args.case_in_file)

            run_commands(split_commands(args.post_run), sim_dir, "", "", cov_dir, urg_report)
            if not split_commands(args.post_run):
                generate_urg_report(sim_dir, args.cov_path, args.urg_cmd, True)
            print("Coverage after adjustment:")
            group = print_status(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, args.status_limit)
            if group is None or group + 1e-06 < args.target:
                pass
            print("Functional coverage target {:.2f}% was not reached.".format(args.target))
            return 2
        print("Functional coverage target reached: GROUP={:.2f}%".format(group))
        return 0


def parse_current_cover_vars(args, sim_dir, hints):
    cover_vars = safe_parse_group_variables(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, hints)
    if not cover_vars:
        cover_vars = cover_vars_from_sv(sim_dir, hints)
    return cover_vars


def run_regress_commands(args, sim_dir, case_list_path, case_root):
    cov_dir, urg_report = command_cov_paths(sim_dir, args.cov_path)
    case_list_rel = os.path.relpath(case_list_path, sim_dir) if case_list_path else args.case_list
    run_commands(single_command(args.regress_cmd), sim_dir, "", "", cov_dir, urg_report, case_list_rel, case_root, args.case_in_file)
    run_commands(split_commands(args.post_run), sim_dir, "", "", cov_dir, urg_report, case_list_rel, case_root, args.case_in_file)
    if not split_commands(args.post_run):
        generate_urg_report(sim_dir, args.cov_path, args.urg_cmd, True)


def run_closure_with_regress_cmd(args, sim_dir, template_case, cover_vars, hints):
    if not args.case_list:
        print("close mode with --regress-cmd requires --case-list, for example xxxx.lst.", file=sys.stderr)
        return 1
    else:
        line_format = resolve_case_list_format(args.case_list_format, hints, args.case_in_file)
        generated_cases_dir = effective_cases_dir(args.cases_dir, line_format, sim_dir, template_case)
        case_root = effective_case_root_for_lst(sim_dir, template_case, generated_cases_dir, line_format)
        print("Case root passed to regression command: {}".format(case_root))
        print("Current coverage before adjustment:")
        group = print_status(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, args.status_limit)
        if group is not None and group + 1e-06 >= args.target:
            print("Functional coverage target already reached: GROUP={:.2f}%".format(group))
            return 0
        cov_dir, urg_report = command_cov_paths(sim_dir, args.cov_path)
        case_list_path_for_cmd = effective_case_list_path(sim_dir, args.case_list_dir, args.case_list)
        case_list_rel_for_cmd = os.path.relpath(case_list_path_for_cmd, sim_dir) if case_list_path_for_cmd else args.case_list
        run_commands(single_command(args.compile_cmd), sim_dir, "", "", cov_dir, urg_report, case_list_rel_for_cmd, case_root, args.case_in_file)
        max_iterations = max(1, args.max_iterations)
        all_cases = []
        for iteration in range(max_iterations):
            if iteration:
                cover_vars = parse_current_cover_vars(args, sim_dir, hints)
            if not cover_vars:
                print("No functional coverpoints were found for coverage closure.", file=sys.stderr)
                return 1
            prefix = args.prefix if max_iterations == 1 else "{}iter{:02d}_".format(args.prefix, iteration)
            cases = write_cases(sim_dir, template_case, cover_vars, prefix, generated_cases_dir, args.max_cross_cases, hints, args.case_in_file)
            for case in cases:
                if case not in all_cases:
                    all_cases.append(case)
                    continue

            case_list_path = write_case_list(sim_dir, generated_cases_dir, all_cases, args.case_list, line_format, args.case_list_dir, args.case_in_file)
            run_regress_commands(args, sim_dir, case_list_path, case_root)
            print("Coverage after adjustment iteration {}:".format(iteration + 1))
            group = print_status(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, args.status_limit)
            if group is not None and group + 1e-06 >= args.target:
                print("Functional coverage target reached: GROUP={:.2f}%".format(group))
                return 0

        print("Functional coverage target {:.2f}% was not reached.".format(args.target))
        return 2


def main():
    parser = argparse.ArgumentParser(description="Generate config cases from one tc template and same-name coverpoints.")
    parser.add_argument("mode", choices=["status", "generate", "close"], help="operation mode")
    parser.add_argument("--sim-dir", default=".", help="project simulation directory")
    parser.add_argument("--template-case", default="cases/tc_full_pipeline_random.in", help="input tc case template")
    parser.add_argument("--cases-dir", default="cases", help="directory for generated cases")
    parser.add_argument("--prefix", default="tc_auto_func_cov_", help="generated case name prefix")
    parser.add_argument("--cov-path", default=DEFAULT_COV_PATH, help="coverage path containing urgReport or VCS/Verdi .vdb")
    parser.add_argument("--dashboard", default=DEFAULT_DASHBOARD, help="URG dashboard path, or auto")
    parser.add_argument("--grpinfo", default=DEFAULT_GRPINFO, help="URG group info path, or auto")
    parser.add_argument("--urg-cmd", default="urg", help="URG command used to build text reports from .vdb")
    parser.add_argument("--target", type=float, default=100.0, help="required GROUP coverage for close mode")
    parser.add_argument("--status-limit", type=int, default=20, help="maximum missing coverpoints to print")
    parser.add_argument("--max-cross-cases", type=int, default=0, help="maximum generated combinations per cross coverpoint; 0 means no limit")
    parser.add_argument("--hints", default="", help="optional JSON hints from Qwen: aliases and pair constraints")
    parser.add_argument("--pre-run", default="", help="optional compile/setup command template")
    parser.add_argument("--run-case", default="", help="required by close mode; may use {case}, {case_file}, {cov_dir}, {urg_report}")
    parser.add_argument("--post-run", default="", help="optional report command template; empty means auto-run urg from --cov-path")
    parser.add_argument("--compile-cmd", default="", help="project compile command; may use {sim_dir}, {cov_dir}, {urg_report}, {case_list}, {cases_dir}")
    parser.add_argument("--regress-cmd", default="", help="project regression command rerun after generated cases/lst are updated")
    parser.add_argument("--case-list", default="", help="tc case lst filename/path generated from the new cases, for example xxxx.lst")
    parser.add_argument("--case-list-dir", default="", help="directory where the generated tc case lst file is written; ignored when --case-list is absolute or already contains a directory")
    parser.add_argument("--case-list-format", default="auto", help="lst line format; auto uses LLM hints, fallback {case_file}")
    parser.add_argument("--case-in-file", default="", help="fixed .in filename inside each generated case directory; empty keeps legacy cases_dir/case_name.in layout")
    parser.add_argument("--max-iterations", type=int, default=1, help="maximum generate-regress coverage closure iterations")
    args = parser.parse_args()
    sim_dir = os.path.abspath(os.path.expanduser(args.sim_dir))
    template_case = resolve_path(sim_dir, args.template_case)
    hints = load_hints(resolve_path(sim_dir, args.hints)) if args.hints else {}
    if args.mode == "status":
        cover_vars = parse_group_variables(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, hints)
    else:
        cover_vars = safe_parse_group_variables(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, hints)
    if not cover_vars:
        if args.mode in ('generate', 'close'):
            cover_vars = cover_vars_from_sv(sim_dir, hints)
    if args.mode == "status":
        print_status(sim_dir, args.dashboard, args.grpinfo, args.cov_path, args.urg_cmd, args.status_limit)
        return 0
    if not os.path.exists(template_case):
        print("Template case not found: {}".format(template_case), file=sys.stderr)
        return 1
    if args.mode == "generate":
        line_format = resolve_case_list_format(args.case_list_format, hints, args.case_in_file)
        generated_cases_dir = effective_cases_dir(args.cases_dir, line_format, sim_dir, template_case)
        case_root = effective_case_root_for_lst(sim_dir, template_case, generated_cases_dir, line_format)
        print("Case root for lst resolution: {}".format(case_root))
        cases = write_cases(sim_dir, template_case, cover_vars, args.prefix, generated_cases_dir, args.max_cross_cases, hints, args.case_in_file)
        write_case_list(sim_dir, generated_cases_dir, cases, args.case_list, line_format, args.case_list_dir, args.case_in_file)
        return 0
    if not split_commands(args.run_case) and not single_command(args.regress_cmd):
        print("close mode requires either --run-case or --regress-cmd. For portable projects, pass --compile-cmd, --regress-cmd, --cases-dir, and --case-list.", file=sys.stderr)
        return 1
    return run_closure(args, sim_dir, template_case, cover_vars, hints)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print("", file=sys.stderr)
        print("Coverage closure sub-command failed.", file=sys.stderr)
        print("  command: {}".format(exc.cmd), file=sys.stderr)
        print("  exit status: {}".format(exc.returncode), file=sys.stderr)
        print("Fix the command or case/lst paths above, then retry from qwen_cov_close.", file=sys.stderr)
        sys.exit(exc.returncode or 1)
    except KeyboardInterrupt:
        print("Canceled by user.", file=sys.stderr)
        sys.exit(130)

# okay decompiling .\image_processing_cfg_ip\sim\scripts\__pycache__\auto_func_cov.cpython-33.pyc
