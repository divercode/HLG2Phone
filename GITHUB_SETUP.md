# GitHub 仓库设置指南

## 前置步骤：配置 Git 用户信息

在提交代码之前，需要先配置 Git 用户信息：

```bash
# 配置全局用户信息（推荐）
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# 或者仅为当前仓库配置
git config user.name "Your Name"
git config user.email "your.email@example.com"
```

## 步骤 1：在 GitHub 上创建新仓库

1. 登录 GitHub 账号
2. 点击右上角的 "+" 号，选择 "New repository"
3. 填写仓库信息：
   - **Repository name**: `sonyToPhoto` 或 `HLG2Phone`（推荐）
   - **Description**: `Sony HLG 视频转码工具 - 支持GPU加速的批量视频转码工具`
   - **Visibility**: 选择 Public 或 Private
   - **不要**勾选 "Initialize this repository with a README"（因为我们已经有了）
4. 点击 "Create repository"

## 步骤 2：连接本地仓库到 GitHub

在项目目录下执行以下命令（将 `YOUR_USERNAME` 替换为你的 GitHub 用户名，`REPO_NAME` 替换为仓库名）：

```bash
# 添加远程仓库
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# 或者使用 SSH（如果已配置 SSH key）
# git remote add origin git@github.com:YOUR_USERNAME/REPO_NAME.git

# 查看远程仓库配置
git remote -v
```

## 步骤 3：推送代码到 GitHub

```bash
# 推送代码到 GitHub（首次推送）
git branch -M main
git push -u origin main
```

如果遇到分支名称问题，可以使用：
```bash
# 如果默认分支是 master
git push -u origin master
```

## 步骤 4：验证

1. 访问你的 GitHub 仓库页面
2. 确认所有文件都已上传
3. 确认 README.md 正确显示

## 后续更新

如果修改了代码，使用以下命令更新 GitHub：

```bash
# 添加所有更改
git add .

# 提交更改
git commit -m "描述你的更改"

# 推送到 GitHub
git push
```

## 注意事项

- `.gitignore` 文件已配置，以下文件**不会**被提交：
  - 配置文件（`sonyToPhoto_config.json`）
  - 日志文件（`*.log`）
  - 打包后的 EXE 文件
  - 构建临时文件（`build/`, `dist/`）
  - Python 缓存文件（`__pycache__/`）

- **重要**：`Project/` 目录中的 `ffmpeg.exe` 等文件可能较大，如果 GitHub 有文件大小限制，可以考虑：
  - 使用 Git LFS（Large File Storage）
  - 或者不提交这些文件，在 README 中说明需要用户自行下载

## 可选：添加 GitHub Actions 自动打包

如果需要，可以创建 `.github/workflows/build.yml` 来自动打包（需要配置 PyInstaller）。

