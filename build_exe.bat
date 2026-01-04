@echo off
REM 启用延迟变量扩展，避免变量设置问题
setlocal enabledelayedexpansion

chcp 65001 >nul
echo ========================================
echo HLG2Phone 自动打包脚本
echo ========================================
echo.

REM 设置工作目录为脚本所在目录
cd /d "%~dp0"

REM 如果切换目录失败，显示错误并退出
if errorlevel 1 (
    echo [错误] 无法切换到脚本所在目录
    pause
    exit /b 1
)

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python
    pause
    exit /b 1
)

REM 检查PyInstaller是否安装
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [信息] 正在安装PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller安装失败
        pause
        exit /b 1
    )
)

echo [信息] 检查依赖文件...
if not exist "transcode_core.py" (
    echo [错误] 未找到依赖文件 transcode_core.py
    pause
    exit /b 1
)

if not exist "Project\ffmpeg.exe" (
    echo [警告] 未找到 Project\ffmpeg.exe，打包将继续但可能影响功能
)

REM 检查图标文件（使用相对路径，避免路径问题）
set ICON_OPTION=
set USE_ICON=0
if exist "icon.ico" (
    echo [信息] 找到图标文件 icon.ico
    REM 验证图标文件大小（空文件或损坏的文件会导致错误）
    for %%F in ("icon.ico") do set ICON_SIZE=%%~zF
    if !ICON_SIZE! GTR 0 (
        set ICON_OPTION=--icon=icon.ico
        set USE_ICON=1
        echo [信息] 将使用图标: icon.ico (大小: !ICON_SIZE! 字节)
    ) else (
        echo [警告] 图标文件 icon.ico 大小为0，可能已损坏，将跳过图标
    )
) else (
    echo [信息] 未找到 icon.ico，将使用默认图标
    echo [提示] 如需自定义图标，请将有效的ico格式图标文件命名为 icon.ico 并放在项目根目录
)

REM 如果图标文件有问题，询问是否继续
if !USE_ICON!==0 (
    echo [提示] 将使用默认图标进行打包
)

echo.
echo [信息] 开始打包...
echo [保护] 配置文件 sonyToPhoto_config.json 和日志文件 Stdout.log 将被保护，不会被删除
echo.

REM 构建PyInstaller命令
REM 注意：Windows下--add-data使用分号分隔，格式为"源路径;目标路径"
REM 注意：图标参数使用相对路径，放在--onefile之前
set PYINSTALLER_CMD=pyinstaller

REM 添加基本参数
set PYINSTALLER_CMD=!PYINSTALLER_CMD! ^
    --name=HLG2Phone ^
    --onefile ^
    --windowed

REM 如果有有效的图标，添加图标参数（在--onefile之后，使用相对路径）
if !USE_ICON!==1 (
    set PYINSTALLER_CMD=!PYINSTALLER_CMD! !ICON_OPTION!
)

       REM 继续添加其他参数
       set PYINSTALLER_CMD=!PYINSTALLER_CMD! ^
           --add-data "transcode_core.py;." ^
           --add-data "help.html;." ^
           --add-data "about.html;." ^
           --add-data "Project\ffmpeg.exe;Project" ^
           --add-data "Project\ffplay.exe;Project" ^
           --add-data "Project\ffprobe.exe;Project" ^
    --hidden-import=transcode_core ^
    --hidden-import=PyQt5.QtCore ^
    --hidden-import=PyQt5.QtWidgets ^
    --hidden-import=PyQt5.QtGui ^
    --hidden-import=psutil ^
    --hidden-import=json ^
    --hidden-import=subprocess ^
    --hidden-import=threading ^
    --hidden-import=datetime ^
    --hidden-import=pathlib ^
    --hidden-import=atexit ^
    --collect-all=PyQt5 ^
    --noconsole ^
    --clean ^
    sonyToPhoto.py

echo [信息] 执行命令: !PYINSTALLER_CMD!
echo.

REM 执行打包命令
!PYINSTALLER_CMD!

REM 如果打包失败且使用了图标，尝试不使用图标重新打包
if errorlevel 1 (
    if !USE_ICON!==1 (
        echo.
        echo [警告] 使用图标打包失败，尝试不使用图标重新打包...
        echo.
        
               REM 重新构建命令（不使用图标）
               set PYINSTALLER_CMD=pyinstaller ^
                   --name=HLG2Phone ^
                   --onefile ^
                   --windowed ^
                   --add-data "transcode_core.py;." ^
                   --add-data "help.html;." ^
                   --add-data "about.html;." ^
                   --add-data "Project\ffmpeg.exe;Project" ^
                   --add-data "Project\ffplay.exe;Project" ^
                   --add-data "Project\ffprobe.exe;Project" ^
            --hidden-import=transcode_core ^
            --hidden-import=PyQt5.QtCore ^
            --hidden-import=PyQt5.QtWidgets ^
            --hidden-import=PyQt5.QtGui ^
            --hidden-import=psutil ^
            --hidden-import=json ^
            --hidden-import=subprocess ^
            --hidden-import=threading ^
            --hidden-import=datetime ^
            --hidden-import=pathlib ^
            --hidden-import=atexit ^
            --collect-all=PyQt5 ^
            --noconsole ^
            --clean ^
            sonyToPhoto.py
        
        echo [信息] 执行命令（无图标）: !PYINSTALLER_CMD!
        echo.
        
        !PYINSTALLER_CMD!
        
        if errorlevel 1 (
            echo.
            echo [错误] 打包失败！即使不使用图标也失败，请检查其他错误信息
            pause
            exit /b 1
        ) else (
            echo.
            echo [警告] 已成功打包，但未使用自定义图标（使用默认图标）
            echo [提示] 请检查 icon.ico 文件是否有效，或删除该文件后重新打包
        )
    ) else (
        echo.
        echo [错误] 打包失败！
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo [成功] 打包完成！
echo ========================================
echo.

REM 检查生成的文件
if exist "dist\HLG2Phone.exe" (
    echo [信息] 已成功生成 HLG2Phone.exe
    echo [信息] 文件大小:
    dir "dist\HLG2Phone.exe" | findstr "HLG2Phone.exe"
    echo.
    
    REM 1. 自动删除 build 文件夹
    if exist "build" (
        echo [信息] 正在删除 build 目录...
        rmdir /s /q "build"
        echo [信息] 已删除 build 目录
    )
    
    REM 2. 将 dist 文件夹的 exe 文件剪切到根文件夹下
    echo [信息] 正在移动 HLG2Phone.exe 到根目录...
    move /y "dist\HLG2Phone.exe" "HLG2Phone.exe" >nul 2>&1
    if exist "HLG2Phone.exe" (
        echo [信息] 已成功移动 HLG2Phone.exe 到根目录
    ) else (
        echo [错误] 移动 exe 文件失败
        pause
        exit /b 1
    )
    
    REM 3. 删除 dist 文件夹
    if exist "dist" (
        echo [信息] 正在删除 dist 目录...
        rmdir /s /q "dist"
        echo [信息] 已删除 dist 目录
    )
    
    REM 删除 spec 文件
    if exist "HLG2Phone.spec" (
        del /q "HLG2Phone.spec" >nul 2>&1
    )
    
    echo.
    echo ========================================
    echo [完成] 所有操作已完成！
    echo ========================================
    echo.
    echo [信息] HLG2Phone.exe 已移动到根目录
    echo [信息] 正在启动程序...
    echo.
    
    REM 4. 直接运行生成后的 exe 文件
    start "" "HLG2Phone.exe"
    echo [信息] 程序已启动
) else (
    echo [错误] 未找到生成的exe文件
    pause
    exit /b 1
)

REM 脚本执行完成
endlocal

