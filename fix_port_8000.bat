@echo off
echo ============================================================
echo   修复 8000 端口 - 从 Hyper-V WinNAT 保留范围中释放
echo ============================================================
echo.
echo 正在停止 WinNAT 服务...
net stop winnat
echo.
echo 正在添加 8000 端口排除（使其不被 WinNAT 动态占用）...
netsh int ipv4 add excludedportrange protocol=tcp startport=8000 numberofports=1 store=persistent
echo.
echo 正在重新启动 WinNAT 服务...
net start winnat
echo.
echo ============================================================
echo   完成！8000 端口已释放，现在可以启动服务了
echo ============================================================
echo.
pause