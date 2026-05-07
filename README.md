# Qwen/Llama Coverage Closure Portable Bundle

这是一个可迁移的功能覆盖率自动闭环工具包，用于 VCS/Verdi 项目中基于配置文件生成用例、运行回归并收敛功能覆盖率。工具支持本地 LLM 参与项目适配和复杂 cross 覆盖率分析。

工具包内置：

- `bin/qwen_cov_agent.py`：交互式入口，负责 LLM 适配、参数确认、失败后修正对话。
- `bin/auto_func_cov.py`：确定性覆盖率闭环引擎，负责解析 case 模板、覆盖率报告、生成补充 case 和 lst。
- `bin/ollama` 及 `lib/ollama`：内置 Ollama 运行时。
- `runtime/python-3.3.3`：内置 Python 运行时。
- `models`：本地模型目录，例如 Qwen/Llama instruct 模型。
- glibc 运行时包装：用于旧 Linux 设备上直接启动 Ollama。

目标设备仍需要项目本身的 EDA 环境，例如 `vcs`、`urg`、`verdi`、`make`。

## 1. 快速启动

在 Linux 设备上解包后进入目录：

```bash
cd qwen_cov_closure_linux_portable_20260507_224310
bash run_qwen_cov_agent.sh --interactive
```

真实跑覆盖率闭环时不要加 `--analysis-only`。该模式只做设置检查和确认，不会编译、生成 case、运行回归或刷新覆盖率。

## 2. 推荐 Makefile 入口

项目 `sim/Makefile.vcs` 中建议添加或使用类似入口：

```make
qwen_cov_close:
	bash /path/to/qwen_cov_closure_linux_portable_20260507_224310/run_qwen_cov_agent.sh --interactive \
	  --sim-dir $(CURDIR) \
	  --template-case $(FUNC_COV_TEMPLATE) \
	  --cov-path $(FUNC_COV_PATH) \
	  --cases-dir $(FUNC_COV_CASES_DIR) \
	  --case-list-dir $(FUNC_COV_CASE_LIST_DIR) \
	  --case-list $(FUNC_COV_CASE_LIST) \
	  --case-list-format '$(FUNC_COV_CASE_LIST_FORMAT)' \
	  --case-in-file '$(FUNC_COV_CASE_IN_FILE)' \
	  --compile-cmd '$(FUNC_COV_COMPILE_CMD)' \
	  --regress-cmd '$(FUNC_COV_REGRESS_CMD)' \
	  --max-iterations $(FUNC_COV_MAX_ITER)
```

然后运行：

```bash
make -f Makefile.vcs qwen_cov_close
```

## 3. 交互输入项

启动后工具会逐项确认：

```text
0) project sim directory
1) LLM model choice
2) tc case template file
3) coverage path
4) generated tc case directory
5) generated tc case lst directory
6) generated tc case lst filename
7) tc case lst line format
8) fixed .in filename inside each case dir
9) compile command
10) regression command
11) max closure iterations
12) max cases per cross coverpoint
13) target GROUP coverage percent
14) LLM timeout seconds
15) URG command
```

重要规则：

- `template-case` 如果是用户输入的绝对文件路径，工具会保持原样，不会自动改写。
- `cases-dir` 是生成 case 的根目录，工具不会因为回归执行目录不同而擅自改掉它。
- `case-list-dir` 是生成 lst 文件的位置。
- `case-list-format` 描述 lst 每一行写什么。
- `case-in-file` 描述每个 case 目录内部固定的 `.in` 文件名。

## 4. 目录型 case 模式

现在支持这种结构：

```text
cases/
  auto_llama/
    tc_auto_func_cov_00/
      config.in
    tc_auto_func_cov_01/
      config.in
```

对应输入：

```bash
--cases-dir cases
--case-list-format 'auto_llama/{case}'
--case-in-file config.in
```

生成的 lst 内容是 case 目录路径，不带 `.in`：

```text
auto_llama/tc_auto_func_cov_00
auto_llama/tc_auto_func_cov_01
```

回归命令中传入：

```bash
make -f Makefile.vcs run_lst TC_LIST={case_list} CASE_ROOT={cases_dir} CASE_IN_FILE={case_in_file}
```

`run_lst` 会自动把 lst 行解析为：

```text
cases/auto_llama/tc_auto_func_cov_00/config.in
```

如果 `--case-in-file` 为空，则保持旧模式：每个 case 直接是一个 `.in` 文件，例如 `cases/auto_llama/tc_auto_func_cov_00.in`。

## 5. case 模板格式

case 文件每一行格式：

```text
项名     是否随机     配置值或随机范围
```

含义：

| 字段 | 含义 |
| --- | --- |
| 项名 | 配置项名，尽量与 RTL/TB 中配置名和功能覆盖率 coverpoint 名一致 |
| 是否随机 | `0` 表示定值，`1` 表示随机 |
| 配置值或随机范围 | 定值如 `1`，范围如 `(0,100)`；使用范围时是否随机必须为 `1` |

示例：

```text
case_name                    0            tc_template
random_seed                  0            9100
function                     0            0
brightness_value             1            (0,100)
red_enable                   0            1
green_enable                 0            1
blue_enable                  0            1
threshold_enable             0            0
threshold_value              1            (0,255)
```

## 6. 覆盖率输入

用户只需要输入覆盖率路径，例如：

```bash
--cov-path cov
```

工具优先读取：

```text
cov/urgReport/dashboard.txt
cov/urgReport/grpinfo.txt
```

如果没有找到这两个文件，但 `cov` 下存在 VCS/Verdi 覆盖率数据库，例如：

```text
cov/simv.vdb
```

工具会自动调用：

```bash
urg -full64 -dir cov/simv.vdb -report cov/urgReport -format both
```

## 7. 覆盖率映射提示说明

运行时可能看到：

```text
Case/code mapping summary:
total_case_items=13
matched_to_coverpoint=7
missing_code_refs=0
code_refs_but_no_coverpoint=6
unmatched_coverpoints=0
```

含义：

- `total_case_items`：case 模板里解析到的全部配置项数量。
- `matched_to_coverpoint`：已经匹配到功能覆盖率 coverpoint 的配置项数量。
- `missing_code_refs`：case 项在代码里找不到明显引用。
- `code_refs_but_no_coverpoint`：代码里有引用，但没有匹配到同名 coverpoint。
- `unmatched_coverpoints`：功能覆盖率中存在，但没匹配到 case 模板项的 coverpoint。

例如：

```text
Informational: case items with code references but no matching coverpoint:
  case_name
  random_seed
  pixel_count
  pixel_red
  pixel_green
  pixel_blue
```

这不是“只识别到了这些项”，而是这些项没有功能覆盖率 coverpoint。通常 `case_name`、`random_seed`、随机 pixel 数据项不需要作为功能覆盖率配置项。

## 8. LLM 的作用

LLM 不是替代确定性覆盖率脚本，而是做项目适配：

- 根据 case 模板项名、RTL/TB 信号名、coverpoint 名做别名匹配。
- 分析复杂 cross coverpoint 需要哪些配置组合。
- 在输入格式不准确或回归失败时，给出修正建议。
- 必要时生成受控 patch，修改项目适配代码。交互模式会先确认再应用。

## 9. 常用命令

交互运行：

```bash
bash run_qwen_cov_agent.sh --interactive
```

非交互示例：

```bash
bash run_qwen_cov_agent.sh \
  --sim-dir /path/to/project/sim \
  --model-choice llama \
  --template-case /path/to/project/sim/cases/tc_template.in \
  --cov-path cov \
  --cases-dir cases \
  --case-list-dir lists \
  --case-list auto_func_cov_cases.lst \
  --case-list-format 'auto_llama/{case}' \
  --case-in-file config.in \
  --compile-cmd 'make -f Makefile.vcs clean; make -f Makefile.vcs compile' \
  --regress-cmd 'make -f Makefile.vcs run_lst TC_LIST={case_list} CASE_ROOT={cases_dir} CASE_IN_FILE={case_in_file} DUMP=0 COV_DIR={cov_dir} URG_RPT={urg_report}' \
  --max-iterations 3 \
  --max-cross-cases 100
```

只检查配置，不运行回归：

```bash
bash run_qwen_cov_agent.sh --interactive --analysis-only
```

## 10. 打包仓库分卷恢复

如果该工具是从 GitHub public 仓库下载的，并且 portable 包被拆成多个小于 100MB 的分卷，进入仓库后执行：

```bash
bash scripts/restore_portable_bundle.sh
```

恢复完成后会得到：

```text
dist/qwen_cov_closure_linux_portable_20260507_224310.tar
```

然后解包：

```bash
tar -xf dist/qwen_cov_closure_linux_portable_20260507_224310.tar -C dist
```

## 11. 注意事项

- public GitHub 普通仓库单文件大小限制是 100MB，因此大模型和运行时必须分卷提交。
- 如果从 Windows 拷贝到 Linux，启动脚本会自动修复 Ollama 相关执行权限和 `.so` 链接。
- 如果项目在 `/mnt/hgfs` 共享目录下，工具可自动迁移到 VM 本地目录运行，避免 VCS 创建符号链接失败。
- `template-case` 会保持用户输入，不会被迁移路径逻辑擅自改写。
