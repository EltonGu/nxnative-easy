# 黑屏修复：Mac 着色器库改为按应用最低系统（macOS 26.6）构建

本文记录一个 macOS 打包黑屏问题的完整排查与修复：问题表象、问题原因、修复办法、验证方案，以及本次改动内容。

适用对象：在较新的 Mac（如 macOS 27.1 / 27.2 + Xcode 27.2）上打包 nxnative Mac 应用，分发到较旧系统（如 macOS 26.6）的同学机器后出现**一直黑屏**的场景。

---

## 一、问题表象

### 1.1 玩家看到的现象

- 打好的 `.app` 包，在**打包那台 Mac 上正常**，在**其他 Mac 上打开后一直黑屏**，放一整晚仍是黑屏。
- 窗口是存在的（能看到一个黑色窗口，而不是"没有窗口"）。
- 程序**没有崩溃**，任务管理器里 CPU 占用正常，音频也在正常播放。

### 1.2 日志里的决定性证据

日志（`[dm]` 前缀为宿主输出）中，启动几十秒内集中出现**数百到数千行** `[RED]` 报错，形如：

```
[dm] [nvn-mtl] [RED] failed to load shader 0323b640ea6cd454_b: This library is using language version 4.1 which is not supported on this OS.
[dm] [nvn-mtl] [RED] shader 0323b640ea6cd454 (vertex) failed to load: build the shaders with dm/gfx/tools/dmsh_build.py first
[dm] [nvn-mtl] [RED] program has no vertex shader (or it is not mapped)
[dm] [nvn-mtl] [RED] the dispatched program has no compute shader
```

与此同时，还有其他正常指标，**它们证明问题不在崩溃或卡死**：

- 帧率稳定在 59.6–59.8 fps
- `nnMain` 已进入、RomFS 与 aoc（DLC）挂载成功
- 存档 `save commit #1` 成功落盘
- 窗口已创建（`WindowInitialize swap chain ... 1920x1080`）
- 音频 0 underrun

**结论**：进程活着、引擎在持续出帧，但**画面内容是空的**——所有绘制都被跳过了。

### 1.3 同一条报错的第二层

日志中还有一条与之同源的报错，同时指向了"版本错配"：

```
[dm] [nvn-mtl] pipeline archive bundled with the app: this system cannot open .../pso/applegpu_g16g.mtl4a
      (deployment target for architecture applegpu_g16g found in archive ... is not compatible with current OS;
       made for another system version, or an OS update changed the GPU compiler): the bases are built on the device
```

### 1.4 关键交叉验证

同一份包，在两台不同的机器上（一台 M1 Max、一台 M4），以及两款不同的游戏（最终幻想共鸣、王国之泪）上，**报错模式完全一致**。这说明：

- **不是某一台机器的偶发问题**
- **不是芯片型号问题**（M1 Max 与 M4 都失败）
- **不是某一款游戏的问题**
- 而是**这个打包产物对所有较旧系统都不兼容**

统计对照：

| 机器 / 游戏 | GPU | shader 加载失败条数 | 报错文本 |
|---|---|---|---|
| 机器 A · 最终幻想共鸣 | Apple M1 Max | 337 | `language version 4.1 ... not supported` |
| 机器 B · 最终幻想共鸣 | Apple M4 | 337 | 同上 |
| 机器 B · 王国之泪 | Apple M4 | 2942 | 同上 |

---

## 二、问题原因

### 2.1 一句话原因

**打包时编译分发用的游戏着色器，没有指定 `-mmacosx-version-min`，于是 `xcrun metal` 采用了打包机 SDK 的部署目标（27.x），产出的着色器库带有 MSL 4.1 / 最低 macOS 27 的标记；较旧系统的 Metal 驱动不认识 4.1，于是拒绝加载每一个着色器库，最终什么都不画。**

### 2.2 代码级定位

问题出在 `dm/gfx/tools/dmsh_build.py`（修复前的第 168 行）：

```python
MAC_METAL = ['xcrun', '-sdk', 'macosx', 'metal', '-c', '-O1', '-fpreserve-invariance']
```

注意这里**没有 `-mmacosx-version-min` 参数**。缺省时，`xcrun metal` 会采用所选 SDK 的部署目标——在 Xcode 27.2 上就是 27.0。

**对照证据**：同项目的 iOS 编译路径（`dm/ios/tools/ios_metal.py`）从一开始就写了部署目标：

```python
METAL = ['xcrun', '-sdk', 'iphoneos', 'metal', '-c', '-O1', '-mios-version-min=18.0', ...]
```

即 **iOS 有 `-mios-version-min`，macOS 缺了对应的 `-mmacosx-version-min`**。这是一个遗漏，不是设计。

### 2.3 为什么是"黑屏"而不是"报错退出"

nxnative 的宿主**没有运行时的重新编译回退**。按 `dm/gfx/README.md` 的设计：

> 宿主只从 `b-<V>/` 目录加载着色器库，并逐个校验版本；不匹配就报红并拒绝加载，**不会在运行时重新编译**。

所以着色器全部加载失败后：

1. 引擎照常提交绘制命令
2. 但每次绘制都因为"没有可用的着色器/管线"而被跳过
3. 引擎照常呈现空帧 → **黑屏**，且稳定 60fps

### 2.4 为什么"打包机正常、别的机器黑屏"

| 环境 | 系统支持的语言版本 | 结果 |
|---|---|---|
| 打包机（macOS 27.x） | 支持 4.1 | 库能加载，正常显示 |
| 目标机（macOS 26.6） | 只支持到较低版本 | 拒绝加载，黑屏 |

这正是"**一次打包、只能在自己这台新系统上跑**"的根本原因。

### 2.5 补充：为什么升级系统只能"碰运气"

报错方向是"**产物版本 > 运行端支持版本**"。升级目标机系统可以抬升运行端上限，**方向是对的**，但有两个不确定性：

1. 必须升到其 Metal 驱动**确实支持 4.1** 的那个版本（`v4_1` 是独立枚举值，不是"任意 26.x 都包含"）。
2. 无法保证所有同学机器都升级到恰好匹配的版本。

因此**根治应当从打包端入手**，而不是要求每台目标机升级。

---

## 三、问题修复办法

### 3.1 修复思路

让**着色器库的编译部署目标**与**应用声明的最低系统**保持一致，且这个"最低系统"必须有**唯一的事实来源**。

项目中恰好已有这个事实来源：`dm/mac/min_os.mk`。

```make
MACOS_MIN := 26.6
```

这个文件本来就供两处使用：
- `dm/host/Makefile` 的 `-mmacosx-version-min=$(MACOS_MIN)`（host 二进制的部署目标）
- `pack_app.py` 读取 host 的 `minos`，写入 `Info.plist` 的 `LSMinimumSystemVersion`

**只要让着色器编译也读同一个值**，就能保证：**能打开这个 app 的 Mac，一定能加载它携带的每一个着色器库。**

### 3.2 具体改动

#### ① `dm/gfx/tools/dmsh_build.py` — 加上部署目标

```python
MAC_MIN = os.environ.get('DM_MACOS_MIN') or dmsh_chain.macos_min()
MAC_METAL = ['xcrun', '-sdk', 'macosx', 'metal', '-c', '-O1', f'-mmacosx-version-min={MAC_MIN}', '-fpreserve-invariance']
```

#### ② `dm/gfx/tools/dmsh_chain.py` — 单一事实来源的读取器 + 纳入链版本

新增 `macos_min()`，从 `dm/mac/min_os.mk` 读取 `MACOS_MIN`：

```python
def macos_min():
    """The Mac shader libraries' deployment target: MACOS_MIN in dm/mac/min_os.mk, ..."""
    for line in open(os.path.join(GFX, '../mac/min_os.mk'), encoding='utf-8'):
        line = line.split('#', 1)[0].strip()
        if line.startswith('MACOS_MIN'):
            v = line.split(':=', 1)[1].strip() if ':=' in line else line.split('=', 1)[1].strip()
            if v: return v
    raise SystemExit('[RED] dm/mac/min_os.mk has no MACOS_MIN: the Mac shader libraries need its deployment target')
```

并在 `version()` 中把这个值计入链版本：

```python
h.update(b'dm/mac/min_os.mk\0' + macos_min().encode() + b'\0')
```

**为什么必须计入链版本**：库目录名是 `b-<V>`。若该值不进 V，改完最低版本后仍会命中旧缓存、复用旧库，修复等于没做。

#### ③ `dm/gfx/tools/pso_offline.py` — PSO 归档同步对齐

macOS 的离线管线归档默认值，由"本机主版本"改为"着色器库的最低版本"：

```python
if platform == 'macos':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import dmsh_chain
    return dmsh_chain.macos_min()
```

> **注意（能力边界）**：Metal 4 的管线归档按**主版本**锁定，官方实测：在 macOS 27.2 上无法打开为 26.0/26.6 制作的归档。所以这一项**无法做到"一份归档所有系统通用"**。本改动的效果是：让归档与库声明同一个最低版本，避免包内自相矛盾；在 27.x 机器上首次启动会回退为"在设备上现场构建管线"——**只是慢一点，不是黑屏**。

#### ④ 测试

新增 `dm/tools/tests/test_macos_shader_deployment_target.py`（12 项检查），并更新 `dm/tools/tests/test_pso_offline.py` 中 macOS 默认值相关的用例（原断言硬编码 `26.0`，现改为从 `min_os.mk` 读取）。

### 3.3 改动文件清单

| 文件 | 变更 |
|---|---|
| `dm/gfx/tools/dmsh_build.py` | +6 / -1，编译命令加 `-mmacosx-version-min` |
| `dm/gfx/tools/dmsh_chain.py` | +15，新增 `macos_min()`，纳入链版本 |
| `dm/gfx/tools/pso_offline.py` | +13 / -4，macOS 归档默认对齐 |
| `dm/tools/tests/test_macos_shader_deployment_target.py` | 新增，122 行 |
| `dm/tools/tests/test_pso_offline.py` | +6 / -2，更新 macOS 默认值断言 |

### 3.4 重要：必须整包重建

链版本 V 变了，**不能只替换 shader 目录**，必须按以下顺序重建：

```bash
cd /path/to/nxnative-easy

# 1. 更新链版本头文件
python3 dm/gfx/tools/dmsh_chain.py --header

# 2. 全量重编着色器库（首次约 30–60 分钟）
python3 dm/gfx/tools/dmsh_build.py

# 3. 重新编译 host（因为链版本变了）
make -C dm/host

# 4. 正常打 Mac app 包（--platform mac-app）
python3 scripts/build_ipa_from_nsp.py <游戏目录> -k <prod.keys> --platform mac-app
```

### 3.5 环境要求（务必确认）

| 项目 | 要求 |
|---|---|
| Xcode | **必须 27.2**（精确锁定，非"27.2+"），且需 `sudo xcode-select -s` 选中 |
| Metal 编译器 | **32023.922**（真正的判据） |
| macOS | 26.6 或更高 |
| Metal Toolchain | **先选中 27.2，再**执行 `xcodebuild -downloadComponent MetalToolchain` |

一键自检：

```bash
python3 dm/gfx/tools/own_compilers.py --check-metal
# 无输出 = 通过；有输出 = 会提示缺什么、该装哪个 Xcode
```

---

## 四、修复验证方案

### 4.1 第一步：单元测试（打包机本地，1 分钟）

```bash
cd /path/to/nxnative-easy
python3 -m unittest dm.tools.tests.test_macos_shader_deployment_target -v
```

**预期**：`Ran 12 tests ... OK`

覆盖点：
- 编译命令行必须含 `-mmacosx-version-min=`
- 最低版本取自 `dm/mac/min_os.mk`，而非 `sw_vers`（本机系统）
- 最低版本进入 `MAC_RECORD`（编译缓存 key）
- 最低版本进入链版本 V
- `macos_min()` 能正确处理注释、`:=` 与 `=` 两种赋值、缺失时报错
- PSO 归档 macOS 默认取同一最低版本；iOS 仍取 SDK

同时复核既有用例：

```bash
python3 -m unittest dm.tools.tests.test_pso_offline -v
```

**预期**：在 macOS 上应全部通过。

> 说明：该测试文件在 **Windows** 下有既有失败（`dm/games/game.py` 的 `extra_dirs()` 用硬编码 `:` 分隔 `DM_GAMES_DIR`，Windows 应为 `;`），与本次改动无关，已在未打补丁的原始代码上复现同样失败。此问题不在本次范围。

### 4.2 第二步：确认产物确实变了（打包机，关键）

编译一个 shader 后，检查生成的 `.metallib` 的最低系统版本。可用 `metal-objdump` / `otool` 或直接看构建日志中的编译命令：

**方式一：看编译记录**

```bash
# 构建时打印的编译命令应形如：
# xcrun -sdk macosx metal -c -O1 -mmacosx-version-min=26.6 -fpreserve-invariance ...
```

**方式二：检查产出的库目录**

```bash
# 链版本 V 应当与改动前不同（因为 min_os.mk 的值已计入 V）
python3 dm/gfx/tools/dmsh_chain.py
ls "$DM_ROOT/build/cache/metal_shader_cache/"
```

**预期**：出现一个新的 `b-<新V>` 目录，且其中 `.metallib` 是本次重新编译的。

### 4.3 第三步：目标机实机验证（决定性，在 macOS 26.6 的机器上）

**3.1 打开 app**，让它运行 30 秒以上。

**3.2 找到日志**并搜索关键错误：

```bash
# 日志通常位于 app 的运行目录；也可在终端直接运行宿主以查看实时输出
# 搜索是否还有 language version 报错：
grep -c "language version" <日志文件>
```

**判定标准**：

| 结果 | 含义 | 结论 |
|---|---|---|
| `language version` 报错为 **0 条** | 着色器全部加载成功 | ✅ 修复生效 |
| 仍有大量 `language version` 报错 | 库版本仍不匹配 | ❌ 需检查 §3.4/§3.5 |

**3.3 观察画面**：应能正常进入游戏画面（不再是黑屏）。

**3.4 顺带观察 PSO 相关行为**：可能看到

```
pipeline archive bundled with the app: ... the bases are built on the device
```

这是**预期行为**（跨主版本无法共享归档），首次启动会稍慢，**不是故障**。

### 4.4 第四步：回归确认（可选但推荐）

- 用**打包机本身**（macOS 27.x）再跑一次，确认仍是正常画面（不能"修好了旧的、弄坏了新的"）。
- 对比帧率、显存占用是否与修复前一致。

### 4.5 验证结果记录表（建议填写）

| 项目 | 结果 |
|---|---|
| 单元测试 12 项 | ☐ 全部通过 |
| 链版本 V 已变化 | ☐ 是 |
| 目标机 language version 报错数 | ☐ 0 条 |
| 目标机画面正常 | ☐ 是 |
| 打包机画面仍正常 | ☐ 是 |
| 目标机系统版本（`sw_vers`） | ☐ ______ |
| 打包机 Xcode / Metal 版本 | ☐ ______ / ☐ ______ |

---

## 五、预期效果与能力边界

### 5.1 修复后能达到的

**"一次打包，macOS 26.6 及以上系统都能运行。"**

- 只要目标机系统 ≥ `MACOS_MIN`（当前 26.6），就能加载全部着色器库并正常显示。
- 应用声明的系统门槛与着色器库编译门槛**永远一致**，不会出现"能打开但加载不了"的错位。

### 5.2 明确做不到的

**无法做到"一份包在任意系统版本上完美通用"。**

原因是 Metal 4 的管线归档（`.mtl4a`）按主版本锁定。跨主版本时：

- 归档无法共享 → 目标机首次启动**在现场构建管线**
- 表现：**首次启动较慢**，之后有缓存；**画面正常，不是黑屏**

### 5.3 如需覆盖多个主版本

若要 26.x 与 27.x 都是"完美"（首启也快），需要为每个主版本各出一份归档，例如：

```bash
python3 dm/gfx/tools/pso_offline.py --platform macos --os-min 26.6 --gpu <目标GPU架构>
```

这不属于本次改动范围，属于后续可选优化。

---

## 六、附：本次提交

- 分支：`feature/macos26-universal`
- 提交：`Build the Mac shader libraries for the app's minimum macOS, not the packing SDK's`
- 基线：`main` 分支保持不变，未受任何影响

复现历史问题所需的关键日志特征（便于日后检索）：

```
failed to load shader <KEY>_b: This library is using language version 4.1 which is not supported on this OS
```
