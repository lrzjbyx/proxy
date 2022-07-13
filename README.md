# 代理转发
 
## 需求
    假期期间，需要在家用笔记本访问学校实验室的台式主机。目前主流办法是使用向日葵远程软件，但是免费的软件存在高延时、复制拷贝不灵敏等问题，由此衍生了一种想法是否可以使用window自带的远程控制软件来操作。考虑到两台主机在不同的局域网，要么用代理的方式，要么用P2P打洞的方式。对于P2P的方式实属有点难度，笔者选择使用代理方式来实现吧。
## 原理
 
![Alt](img/1.png)
![Alt](img/2.png)
```
实验室主机和公网服务器建立心跳检测连接、命令管道、转发管道
家里主机访问公网所代理的地址和端口，也会建立转发管道
```

## 需提供
 
```
公网服务器(阿里云\百度云)
服务器系统建议centos7
端口全部开放
```
 
## 使用

```
Server.py 部署到服务器上
根据实际情况更改delegation_port和agent_port
Client.py 部署到实验室主机上
根据实际情况更改服务器地址和代理端口
```

## 演示
![Alt](img/3.png)
![Alt](img/4.png)
