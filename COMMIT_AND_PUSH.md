# 提交代码到 GitHub 的完整步骤

## 1. 配置 Git 用户信息（首次使用需要）

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱@example.com"
```

## 2. 提交代码到本地仓库

```bash
# 查看当前状态
git status

# 添加所有文件（.gitignore 会过滤不需要的文件）
git add .

# 提交代码
git commit -m "Initial commit: Sony HLG 视频转码工具"
```

## 3. 在 GitHub 上创建仓库

1. 登录 GitHub
2. 点击右上角 "+" → "New repository"
3. 填写信息：
   - Repository name: `HLG2Phone` 或 `sonyToPhoto`
   - Description: `Sony HLG 视频转码工具 - 支持GPU加速的批量视频转码工具`
   - 选择 Public 或 Private
   - **不要**勾选 "Initialize this repository with a README"
4. 点击 "Create repository"

## 4. 连接本地仓库到 GitHub

```bash
# 添加远程仓库（替换 YOUR_USERNAME 和 REPO_NAME）
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# 或者使用 SSH
# git remote add origin git@github.com:YOUR_USERNAME/REPO_NAME.git
```

## 5. 推送代码到 GitHub

```bash
# 重命名分支为 main（如果需要）
git branch -M main

# 推送到 GitHub
git push -u origin main
```

如果默认分支是 master：
```bash
git push -u origin master
```

## 注意事项

- `Project/` 目录中的 FFmpeg 可执行文件已添加到 `.gitignore`，不会被提交（文件较大）
- 配置文件、日志文件、EXE 文件等也不会被提交
- 如果遇到认证问题，可能需要配置 GitHub Personal Access Token

