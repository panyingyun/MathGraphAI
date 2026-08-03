---
name: yypancode
description: 简化代码以提高清晰度。在重构代码以提升可读性且不改变行为时使用此技能。当代码可以正常工作但难以阅读、维护或扩展时，或者在审查累积了不必要复杂性的代码时，请应用此技能。
---

# 代码简化

> 受 [Claude Code Simplifier 插件](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/code-simplifier/agents/code-simplifier.md) 启发。此处将其改编为一个适用于任何 AI 编程 agent 的、通用的、过程驱动的技能。

## 概览

在确保行为完全一致的前提下，通过降低复杂性来简化代码。目标不是减少代码行数，而是让代码变得更容易阅读、理解、修改和调试。每次简化都必须通过一个简单的测试：“新团队成员是否能比阅读原代码更快地理解这段代码？”

## 何时使用

- 功能实现已完成且测试通过，但实现方式显得过于笨重
- 代码审查中指出可读性或复杂性问题时
- 遇到深度嵌套的逻辑、冗长的函数或含义模糊的命名时
- 对迫于时间压力编写的代码进行重构时
- 整合分散在多个文件中的相关逻辑时
- 合并导致重复或不一致的更改后

**何时不使用：**

- 代码已经整洁易读——不要为了简化而简化
- 你还不理解代码的作用——在简化前必须先理解
- 代码对性能要求极高，且“简化”版本会导致明显的性能下降
- 你即将彻底重写该模块——简化会被丢弃的代码是浪费精力

## 五项原则

### 1. 完全保留行为

不要改变代码的功能——只改变其表达方式。所有的输入、输出、副作用、错误处理行为以及边缘情况必须保持完全一致。如果你不确定某项简化是否保留了原始行为，请不要执行。

```
每次变更前请自问：
→ 这项修改对每个输入都能产生相同的输出吗？
→ 这项修改是否维持了相同的错误处理行为？
→ 这项修改是否保留了相同的副作用及其执行顺序？
→ 所有现有的测试是否无需修改即可通过？
```

### 2. 遵循项目规范

简化意味着使代码与代码库更加一致，而不是强加个人偏好。在简化前：

```
1. 阅读 CLAUDE.md / 项目规范
2. 研究相邻代码是如何处理类似模式的
3. 在以下方面匹配项目风格：
   - 导入顺序和模块系统
   - 函数声明风格
   - 命名规范
   - 错误处理模式
   - 类型标注深度
```

破坏项目一致性的简化不是真正的简化，而是无谓的变动。

### 3. 清晰胜过精巧

如果精简的代码需要停顿一下才能解析，那么显式的代码优于精简的代码。

```typescript
// 不清晰：密集的嵌套三元运算符
const label = isNew ? 'New' : isUpdated ? 'Updated' : isArchived ? 'Archived' : 'Active';

// 清晰：可读的映射关系
function getStatusLabel(item: Item): string {
  if (item.isNew) return 'New';
  if (item.isUpdated) return 'Updated';
  if (item.isArchived) return 'Archived';
  return 'Active';
}
```

```typescript
// 不清晰：带有内联逻辑的链式 reduce
const result = items.reduce((acc, item) => ({
  ...acc,
  [item.id]: { ...acc[item.id], count: (acc[item.id]?.count ?? 0) + 1 }
}), {});

// 清晰：带有命名的中间步骤
const countById = new Map<string, number>();
for (const item of items) {
  countById.set(item.id, (countById.get(item.id) ?? 0) + 1);
}
```

### 4. 保持平衡

简化存在一种失效模式：过度简化。警惕以下陷阱：

- **过度内联**——移除一个赋予概念名称的辅助函数会使调用处更难理解。
- **合并无关逻辑**——将两个简单的函数合并为一个复杂的函数并不等于简化。
- **移除“不必要”的抽象**——某些抽象是为了扩展性或可测试性而存在的，而非为了增加复杂性。
- **过度追求行数**——减少行数不是目标，更易理解才是。

### 5. 限定变更范围

默认只简化最近修改的代码。除非被明确要求扩大范围，否则避免对无关代码进行“顺带式”重构。无范围限制的简化会在 diff 中产生噪音，并增加引入意外回归的风险。

## 简化流程

### 第一步：动手前先理解（切斯特顿围栏原则）

在更改或移除任何内容前，先搞清楚它为什么存在。这就是切斯特顿围栏原则：如果你在路上看到一道围栏，但不明白它为什么在那儿，就不要拆掉它。先弄清原因，再决定该原因是否仍然成立。

```
在简化前，请回答：
- 这段代码的职责是什么？
- 谁调用它？它调用谁？
- 边缘情况和错误路径有哪些？
- 是否有定义预期行为的测试？
- 为什么它会被写成这样？（性能？平台限制？历史原因？）
- 查看 git blame：这段代码最初的背景是什么？
```

如果你无法回答这些问题，说明你还没准备好进行简化。请先阅读更多上下文。

### 第二步：识别简化机会

扫描以下模式：

**结构复杂性：**

| 模式 | 信号 | 简化方案 |
|---------|--------|----------------|
| 深度嵌套（3层以上） | 控制流难以追踪 | 将条件提取为卫语句 (guard clauses) 或辅助函数 |
| 冗长函数（50行以上） | 多重职责 | 拆分为具有描述性命名的单一职责函数 |
| 嵌套三元运算符 | 解析时需要巨大的脑力栈 | 替换为 if/else 链、switch 或查找对象 |
| 布尔参数标志 | `doThing(true, false, true)` | 替换为选项对象 (options objects) 或独立函数 |
| 重复的条件判断 | 多处出现相同的 `if` 检查 | 提取为命名良好的断言函数 (predicate function) |

**命名与可读性：**

| 模式 | 信号 | 简化方案 |
|---------|--------|----------------|
| 泛泛的命名 | `data`, `result`, `temp`, `val`, `item` | 重命名以描述内容：`userProfile`, `validationErrors` |
| 缩写命名 | `usr`, `cfg`, `btn`, `evt` | 使用完整单词，除非缩写是通用的（`id`, `url`, `api`） |
| 误导性命名 | 名为 `get` 的函数却会修改状态 | 重命名以反映真实行为 |
| 解释“做什么”的注释 | `count++` 上方写着 `// 增加计数器` | 删除注释——代码已经足够清晰 |
| 解释“为什么”的注释 | `// 因 API 在负载下不稳定而重试` | 保留这些——它们承载了代码无法表达的意图 |

**冗余：**

| 模式 | 信号 | 简化方案 |
|---------|--------|----------------|
| 重复逻辑 | 多处出现相同的 5 行以上代码 | 提取为共享函数 |
| 死代码 | 无法触达的分支、未使用的变量、注释掉的代码块 | 移除（在确认确实无用后） |
| 不必要的抽象 | 没有任何价值的包装层 | 内联该包装层，直接调用底层函数 |
| 过度设计的模式 | 为工厂创建的工厂、只有一个策略的策略模式 | 替换为简单的直接处理方式 |
| 冗余类型断言 | 断言一个已经推断出来的类型 | 移除断言 |

### 第三步：增量应用更改

一次只进行一项简化。每次更改后运行测试。**将重构变更与功能开发或 Bug 修复变更分开提交。** 一个既重构又增加功能的 PR 应该是两个 PR——请拆分它们。

```
对于每项简化：
1. 进行修改
2. 运行测试套件
3. 如果测试通过 → 提交（或继续下一项简化）
4. 如果测试失败 → 还原并重新考虑
```

避免将多项简化打包进一个未经测试的变更中。如果出了问题，你需要确切知道是哪项简化导致的。

**500 行原则：** 如果一项重构涉及超过 500 行代码，请投入精力使用自动化工具（codemods, sed 脚本, AST 转换），而不是手动修改。这种规模的手动编辑极易出错且审查压力巨大。

### 第四步：验证结果

在完成所有简化后，退一步评估整体情况：

```
对比前后差异：
- 简化后的版本是否真的更容易理解？
- 你是否引入了与代码库不一致的新模式？
- Diff 是否整洁且易于审查？
- 队友会批准这项更改吗？
```

如果“简化”后的版本反而更难理解或审查，请还原。并不是每次简化尝试都会成功。

## 特定语言指南

### TypeScript / JavaScript

```typescript
// 简化：不必要的 async 包装
// 修改前
async function getUser(id: string): Promise<User> {
  return await userService.findById(id);
}
// 修改后
function getUser(id: string): Promise<User> {
  return userService.findById(id);
}

// 简化：啰嗦的条件赋值
// 修改前
let displayName: string;
if (user.nickname) {
  displayName = user.nickname;
} else {
  displayName = user.fullName;
}
// 修改后
const displayName = user.nickname || user.fullName;

// 简化：手动构建数组
// 修改前
const activeUsers: User[] = [];
for (const user of users) {
  if (user.isActive) {
    activeUsers.push(user);
  }
}
// 修改后
const activeUsers = users.filter((user) => user.isActive);

// 简化：冗余的布尔值返回
// 修改前
function isValid(input: string): boolean {
  if (input.length > 0 && input.length < 100) {
    return true;
  }
  return false;
}
// 修改后
function isValid(input: string): boolean {
  return input.length > 0 && input.length < 100;
}
```

### Python

```python
# 简化：啰嗦的字典构建
# 修改前
result = {}
for item in items:
    result[item.id] = item.name
# 修改后
result = {item.id: item.name for item in items}

# 简化：带早期返回的嵌套条件
# 修改前
def process(data):
    if data is not None:
        if data.is_valid():
            if data.has_permission():
                return do_work(data)
            else:
                raise PermissionError("No permission")
        else:
            raise ValueError("Invalid data")
    else:
        raise TypeError("Data is None")
# 修改后
def process(data):
    if data is None:
        raise TypeError("Data is None")
    if not data.is_valid():
        raise ValueError("Invalid data")
    if not data.has_permission():
        raise PermissionError("No permission")
    return do_work(data)
```

### React / JSX

```tsx
// 简化：啰嗦的条件渲染
// 修改前
function UserBadge({ user }: Props) {
  if (user.isAdmin) {
    return <Badge variant="admin">Admin</Badge>;
  } else {
    return <Badge variant="default">User</Badge>;
  }
}
// 修改后
function UserBadge({ user }: Props) {
  const variant = user.isAdmin ? 'admin' : 'default';
  const label = user.isAdmin ? 'Admin' : 'User';
  return <Badge variant={variant}>{label}</Badge>;
}

// 简化：跨中间组件的属性钻取 (Prop drilling)
// 修改前 —— 考虑使用 Context 或组合 (composition) 是否能更好地解决问题。
// 这是一个权衡判断 —— 请标记出来，不要自动重构。
```

## 常见借口

| 借口 | 现实 |
|---|---|
| “现在能跑，没必要动它” | 难以阅读的代码在出问题时也难以修复。现在简化能为未来的每次更改节省时间。 |
| “行数越少就越简单” | 只有一行的嵌套三元运算符并不比五行的 if/else 更简单。简单是指理解速度，而非代码行数。 |
| “我顺便把这段无关的代码也简化一下” | 无范围限制的简化会产生噪音 diff，并可能在你无意更改的代码中引入回归。请保持专注。 |
| “类型系统已经让它能够自文档化了” | 类型记录的是结构，而非意图。一个命名良好的函数在解释“为什么”方面，比类型签名解释“是什么”要好得多。 |
| “这个抽象以后可能会有用” | 不要保留投机性的抽象。如果现在没用到，它就是没有价值的复杂性。移除它，需要时再加回来。 |
| “原作者肯定有他的理由” | 也许吧。查看 git blame —— 应用切斯特顿围栏原则。但累积的复杂性往往没有任何理由；它只是压力下迭代留下的残余。 |
| “我在增加功能的同时重构” | 将重构与功能开发分开。混合的变更在历史上更难审查、还原和理解。 |

## 危险信号

- 简化后需要修改测试才能通过（你很可能改变了行为）
- “简化”后的代码比原代码更长且更难理解
- 根据个人偏好而非项目规范进行重命名
- 移除错误处理，理由是“让代码更简洁”
- 简化你并不完全理解的代码
- 将许多项简化打包进一个庞大、难以审查的提交中
- 在未经要求的情况下重构当前任务范围之外的代码

## 验证

在完成一轮简化后：

- [ ] 所有现有的测试无需修改即可通过
- [ ] 构建成功且无新警告
- [ ] Linter/Formatter 检查通过
- [ ] 每项简化都是一个可审查的、增量的变更
- [ ] Diff 整洁——没有混入无关的更改
- [ ] 简化后的代码遵循项目规范（参照 CLAUDE.md 或等效文件）
- [ ] 没有任何错误处理被移除或削弱
- [ ] 没有任何死代码被遗留（未使用的导入、无法触达的分支）
- [ ] 队友或审查 agent 会将此变更视为一项实实在在的改进