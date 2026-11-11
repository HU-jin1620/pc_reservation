# 深圳 PC 机时预订系统

一个面向深圳机房 9 台测试主机的轻量级机时预订网站。基于 Flask + SQLite 实现，无需复杂的前后端分离，安装依赖后即可在本机运行。

## 功能特性

- 用户注册 / 登录，登录页提供“保持登录 30 天”选项
- 个人账户弹窗修改密码
- 四个页面：预订列表、设备管理、互联设备、我的预订
- 预订列表：9 台主机 × 24 个小时段，单击空闲格即可预订，单击自己的格子即可取消
- 批量预订：按日期范围和小时范围一次预订多台设备、多个时段
- 我的预订：按设备 + 日期分组展示，支持按时间批量取消
- 设备管理：9 台预设设备，支持搜索、新增、编辑、删除
- 互联设备：每台主机提供“上电 / 断电”虚拟按键，以及全部上电、全部断电

## 技术栈

- Python 3.10+
- Flask 3.x
- SQLite（零配置本地数据库）
- 原生 HTML / CSS / JavaScript

## 目录结构

```text
PC_reserved/
├── app.py                 # 应用入口，含路由、数据库初始化和 API
├── config.py              # 配置，含 SECRET_KEY、HOST、PORT
├── requirements.txt       # Python 依赖
├── start.bat              # Windows 双击后台启动（隐藏窗口）
├── stop.bat               # Windows 双击停止服务
├── start.ps1              # Windows 后台启动脚本
├── stop.ps1               # Windows 停止脚本
├── booking.service        # Linux systemd 服务模板
├── templates/             # 页面模板
├── static/                # CSS、JS、Logo 等静态资源
├── booking.db             # SQLite 数据库（首次运行会自动生成）
└── .secret_key            # 会话签名密钥（首次运行会自动生成）
```

## 环境要求

- Windows / macOS / Linux
- Python 3.10 或更高版本

## 快速开始

在项目目录打开 PowerShell（或对应系统的终端），执行：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

macOS / Linux 下激活虚拟环境使用：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

启动成功后，在浏览器访问：

```text
http://127.0.0.1:5000
```

> 以上是前台启动，关闭 PowerShell 窗口后服务也会停止，只适合本地调试。
> 需要部署到服务器、关闭窗口后继续运行，请看下一节。

## 服务器部署（后台常驻、启动、停止）

### Windows：后台启动

先安装依赖（只需一次）：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

然后双击 `start.bat`，或在项目目录的 PowerShell 中运行：

```powershell
.\start.ps1
```

脚本会用隐藏窗口在后台启动 `app.py`，并把日志写入 `booking.out.log` 和 `booking.err.log`。
关闭 PowerShell 窗口后服务仍会继续运行。

默认监听 `0.0.0.0:5000`，局域网其他机器通过下面的地址访问：

```text
http://服务器局域网IP:5000/
```

要换端口时，先在当前 PowerShell 设置环境变量再启动：

```powershell
$env:PORT = "8000"
.\start.ps1
```

### Windows：查看和停止

查看占用端口的进程：

```powershell
netstat -ano | findstr :5000
```

输出最后一列是 PID。停止服务可以双击 `stop.bat`，或在 PowerShell 中运行：

```powershell
.\stop.ps1
```

也可以手动停止：

```powershell
Stop-Process -Id <PID> -Force
```

如果启动时改了端口，停止前也要设置同样的端口：

```powershell
$env:PORT = "8000"
.\stop.ps1
```

> `Start-Process` 后台进程在用户注销或重启 Windows 后会停止。需要开机自启时，建议把
> `start.bat` 加到 Windows 任务计划程序，或在 Linux 上使用 systemd。

### Linux：systemd 部署（推荐）

1. 把项目放到服务器，例如 `/home/jimmy.xie/PC_reserved`。
2. 安装依赖：

```bash
cd /home/jimmy.xie/PC_reserved
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. 编辑 `booking.service`，把 `User`、`WorkingDirectory`、`ExecStart`、日志路径改成实际值。
4. 安装并启动：

```bash
sudo cp booking.service /etc/systemd/system/booking.service
sudo systemctl daemon-reload
sudo systemctl enable --now booking
```

查看状态和日志：

```bash
sudo systemctl status booking
journalctl -u booking -f
```

停止、重启：

```bash
sudo systemctl stop booking
sudo systemctl restart booking
```

### 防火墙放行端口

局域网或服务器访问不到时，先放行端口。

Windows（管理员 PowerShell）：

```powershell
New-NetFirewallRule -DisplayName "Booking 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

Linux firewalld：

```bash
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload
```

Linux ufw：

```bash
sudo ufw allow 5000/tcp
```

云服务器还需要在云平台的安全组里放行对应端口。

### 查看局域网 IP

Windows：

```powershell
ipconfig
```

Linux：

```bash
hostname -I
```

例如输出 `192.168.100.110`，其他机器就访问 `http://192.168.100.110:5000/`。

## 初始账号

- 用户名：`jimmy.xie`
- 初始密码：`123456`

登录后可在右上角点击用户名，在“个人账户”弹窗中修改密码。首次启动时会自动创建 `jimmy.xie` 账号和 9 台预设设备。

> 如果目录里已经存在旧的 `booking.db`，系统不会覆盖你在其中修改过的密码。

## 使用说明

### 预订列表

页面以表格展示 9 台主机和 24 个小时段（0 点至 23 点）：

- 单击某个空格：预订该主机的该小时，格内显示你的用户名
- 单击自己已预订的格子：取消该预订
- 顶部的批量预订面板：选择设备、开始日期、结束日期和小时范围后，一次预订多个时段

### 设备管理

展示设备的主机名、IP、地区、操作系统、CPU、主板型号、主板厂商和内存。支持：

- 搜索：按主机名、IP 等关键字过滤
- 新增：添加新设备
- 编辑：修改设备信息
- 删除：移除设备（会同时清理该设备的预订和电源状态）

### 互联设备

当前版本提供本地虚拟电源开关，用于演示“上电 / 断电”交互。每台主机都有“上电 / 断电”按键，也可以对全部设备执行“全部上电 / 全部断电”。

如需接入真实的小米电源（米家插座）控制主机上下电，需要补充每台设备对应的小米账号 Token 和设备网关信息。当前代码已预留电源状态表，后续可在 `app.py` 的互联设备 API 中替换为真实控制逻辑。

### 我的预订

按“设备 + 日期”分组展示当前登录用户的所有预订：

- 支持按日期范围和小时范围批量取消
- 点击单个预订可直接取消整个时间段

## 配置说明

可通过环境变量覆盖默认配置：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SECRET_KEY` | 自动生成并保存到 `.secret_key` | 会话签名密钥，用于保持登录 |
| `HOST` | `127.0.0.1` | 监听地址 |
| `PORT` | `5000` | 监听端口 |

示例（Windows PowerShell）：

```powershell
$env:HOST = "0.0.0.0"
$env:PORT = "8000"
python app.py
```

## 数据与备份

- `booking.db`：保存用户、设备、预订和电源状态数据，备份该文件即可备份全部数据
- `.secret_key`：保存会话签名密钥，删除后下次启动会自动生成新密钥，但会使用户已有的“保持登录”失效

这两个文件都属于本地运行数据，首次运行会自动创建，不建议提交到 GitHub。

## 上传 GitHub 前的说明

仓库已提供 `.gitignore`，默认忽略以下内容：

```gitignore
venv/
__pycache__/
*.py[cod]
.secret_key
booking.db
```

提交代码时请勿将 `booking.db` 或 `.secret_key` 上传到公开仓库，以免泄露账号数据和会话密钥。

