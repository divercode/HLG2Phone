# 快速提交到 GitHub

## 第一步：配置 Git（如果还没配置）

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

## 第二步：提交代码

```bash
# 提交所有文件
git commit -m "Initial commit: Sony HLG 视频转码工具"
```

## 第三步：在 GitHub 创建仓库

1. 访问 https://github.com/new
2. 仓库名：`HLG2Phone` 或 `sonyToPhoto`
3. 描述：`Sony HLG 视频转码工具 - 支持GPU加速的批量视频转码工具`
4. 选择 Public 或 Private
5. **不要**勾选 "Initialize this repository with a README"
6. 点击 "Create repository"

## 第四步：连接并推送

```bash
# 添加远程仓库（替换 YOUR_USERNAME 和 REPO_NAME）
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# 推送代码
git branch -M main
git push -u origin main
```

如果提示认证，可能需要使用 Personal Access Token。

## 完成！

访问你的 GitHub 仓库页面，确认代码已成功上传。

