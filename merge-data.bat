@echo off
chcp 65001 >nul
setlocal

:: ============================================================
:: 旧版数据迁移脚本 — Windows
:: ============================================================
::
:: 本脚本会调用 scripts\migrate_legacy_data.py，
:: 把旧版 Windows 客户端的用户数据迁移到当前项目的 data\ 目录。
::
:: 迁移前请先执行 start.bat 启动后端（需要 5409 端口可达）。
:: 脚本会先备份当前 data\ 到 data.bak.YYYYMMDD_HHMMSS\，再迁移数据。

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "DEFAULT_SOURCE=%LOCALAPPDATA%\Social Auto Upload Web UI"
set "PROJECT_DATA=%SCRIPT_DIR%\data"

echo.
echo ============================================================
echo   旧版数据迁移到新版 data\ 目录
echo ============================================================
echo.
echo 需要迁移的源目录说明：
echo.
echo   1) 旧版 Windows 客户端的用户数据目录
echo      路径: %DEFAULT_SOURCE%
echo      包含 cookies\、cookiesFile\、db\、videoFile\ 四个子目录
echo.
echo   2) Github clone 直接启动的项目
echo      路径: %PROJECT_DATA%  (即项目根目录下的 data 目录)
echo.
echo 提示：先执行 start.bat 启动后端，再运行本脚本。
echo.
echo ============================================================
echo.

set "SOURCE="
set /p "choice=请输入选项 1 或 2 (1=旧版Windows客户端, 2=项目data目录), 默认 1: "
if "%choice%"=="" set "choice=1"

if "%choice%"=="1" (
    set "SOURCE=%DEFAULT_SOURCE%"
    if not exist "%SOURCE%" (
        echo.
        echo [错误] 默认目录不存在: %SOURCE%
        echo 请先在 Windows 客户端安装并运行一次旧版程序。
        pause
        exit /b 1
    )
) else if "%choice%"=="2" (
    set "SOURCE=%PROJECT_DATA%"
) else (
    echo.
    echo [错误] 无效选项: %choice%
    pause
    exit /b 1
)

echo.
echo 源目录: %SOURCE%
echo 目标目录: %PROJECT_DATA%
echo.
pause

python "%SCRIPT_DIR%\scripts\migrate_legacy_data.py" --source "%SOURCE%" --target "%PROJECT_DATA%" --yes

endlocal
