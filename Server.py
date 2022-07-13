import socket
import time
import select
import threading
import copy


class Server():

    def __init__(self, port_agents, heart_beat_port=9999):
        # 心跳 端口
        self.heart_beat_port = heart_beat_port
        # 心跳 检测 socket
        self.heart_beat_listen = None
        # 心跳对象维护
        self.socket_map = {
        }
        # 心跳检测列表
        self.heart_beat_connections = []
        # 心跳对象维护锁
        self.socket_map_lock = threading.Lock()
        # 主机存活
        self.ip_live_map = {}
        # 主机存货锁
        self.ip_live_map_lock = threading.Lock()
        # 线程管理
        self.threads = {
            "guard_thread":None,
            "server_thread":[]
        }
        # 服务簇   有多个运行时的服务
        '''
        {
            'heart_beat_listen':'',
            'heart_beat_conn':'',
            'command_listen':'',
            'command_conn':'',
            'server_listen':'',
            'client_listen':'',
            'server_conn':'',
            'client_conn':'',
            'visit_host_time':None
        }

        '''
        self.service_cluster = {}

        # 端口代理服务
        self.port_agents = port_agents

    # 创建心跳检测
    def create_heart_beat_Listen(self):
        self.heart_beat_listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.heart_beat_listen.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.heart_beat_listen.bind(('', self.heart_beat_port))
        self.heart_beat_listen.listen(5)
        self.heart_beat_listen.setblocking(True)
        self.heart_beat_connections.append(self.heart_beat_listen)

        self.socket_map_lock.acquire()
        self.socket_map[self.heart_beat_listen.fileno()] = {"conn": self.heart_beat_listen,
                                                            "add": self.heart_beat_listen.getsockname()}
        self.socket_map_lock.release()

    # 创建监听socket
    def create_listen_socket(self, port):
        _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _socket.bind(('', port))
        _socket.listen(5)
        _socket.setblocking(True)
        return _socket

    # 开启命令监听
    def start_command_listening(self, command_conn, command_listen, _cluster):
        log = "主机{0}:{1}命令通道{2}:{3} <----> {4}:{5}".format(
            self.socket_map[_cluster["heart_beat_conn"]]["conn"].getsockname()[0],
            self.socket_map[_cluster["heart_beat_conn"]]["conn"].getsockname()[1],
            command_listen.getsockname()[0], command_listen.getsockname()[1],
            command_conn.getsockname()[0], command_conn.getsockname()[1])
        print("[INFO] {0} {1}".format(log, "开始服务"))

        connections = [command_conn]

        # for port_agent in self.port_agents:
        #     if _cluster["heart_beat_conn"]["conn"].

        agent_port = None
        client_conn_listening = None
        forward_conn_listening = None
        client_conn = None
        forward_conn = None

        while True:
            if self.ip_live_map[self.socket_map[_cluster["heart_beat_conn"]]["add"][0]] is False:
                return

            rs, ws, es = select.select(connections, [], [])
            for r in rs:
                if r is command_conn:

                    command_msg = r.recv(1024)
                    # print(command_msg)

                    if command_msg == bytes('RESET', encoding='utf-8'):
                        pass
                    elif bytes('DELEGATION', encoding='utf-8') in command_msg:

                        delegation_port = int(command_msg.decode(encoding='utf-8').split(":")[1])
                        for cu in self.port_agents:
                            if cu["delegation_port"] == delegation_port:
                                agent_port = cu["agent_port"]

                        if agent_port is None:
                            print(agent_port)
                            print("[INFO] 端口未申请")

                        # 开启客户端
                        client_conn_listening = self.create_listen_socket(0)
                        _cluster["client_listen"] = client_conn_listening.fileno()
                        # 发送端口信息
                        command_conn.send(
                            bytes('S_MAP_CONN:{0}'.format(client_conn_listening.getsockname()[1]), encoding='utf-8'))
                        print("[INFO] CLIENT PORT LISTENING:{0}".format(client_conn_listening.getsockname()[1]))

                        # 开启服务端
                        forward_conn_listening = self.create_listen_socket(agent_port)
                        _cluster['server_listen'] = forward_conn_listening.fileno()
                        print("[INFO] SERVER PORT LISTENING:{0}".format(forward_conn_listening.getsockname()[1]))

                        self.socket_map_lock.acquire()
                        self.socket_map[client_conn_listening.fileno()] = {"conn": client_conn_listening,
                                                                           "add": client_conn_listening.getsockname()}
                        self.socket_map[forward_conn_listening.fileno()] = {"conn": forward_conn_listening,
                                                                            "add": forward_conn_listening.getsockname()}
                        self.socket_map_lock.release()

                        connections.append(client_conn_listening)
                        connections.append(forward_conn_listening)

                    elif bytes('C_RESET', encoding='utf-8') == command_msg:
                        connections.append(client_conn_listening)
                        connections.append(forward_conn_listening)
                        command_conn.send(
                            bytes('S_MAP_CONN:{0}'.format(client_conn_listening.getsockname()[1]), encoding='utf-8'))



                elif r is client_conn_listening:
                    client_conn, client_add = r.accept()
                    _cluster["client_conn"] = client_conn.fileno()
                    self.socket_map_lock.acquire()
                    self.socket_map[client_conn.fileno()] = {"conn": client_conn,
                                                             "add": client_add}
                    self.socket_map_lock.release()


                    if not client_conn is None and not forward_conn is None :
                        if (not client_conn.fileno() == -1 and not forward_conn.fileno() == -1) :
                            t1 = threading.Thread(target=self.port_forward, args=(client_conn, forward_conn, _cluster))
                            t1.setDaemon(True)
                            t1.start()
                            self.threads["server_thread"].append(t1)


                    connections.remove(client_conn_listening)
                    print("[INFO] 委托主机{0}:{1}连接成功".format(client_add[0], client_add[1]))


                elif r is forward_conn_listening:
                    forward_conn, forward_add = forward_conn_listening.accept()
                    _cluster["server_conn"] = forward_conn.fileno()
                    self.socket_map_lock.acquire()
                    self.socket_map[forward_conn.fileno()] = {"conn": forward_conn,
                                                              "add": forward_add}
                    self.socket_map_lock.release()

                    if not client_conn is None and not forward_conn is None :
                        if not client_conn.fileno() == -1 and not forward_conn.fileno() == -1 :
                            t1 = threading.Thread(target=self.port_forward, args=(client_conn, forward_conn, _cluster))
                            t1.setDaemon(True)
                            t1.start()
                            self.threads["server_thread"].append(t1)


                    connections.remove(forward_conn_listening)
                    print("[INFO] 访问主机{0}:{1}连接成功".format(forward_add[0], forward_add[1]))

    # 端口转发
    def port_forward(self, client_conn, forward_conn, _cluster):

        log = "主机{0}:{1}代理转发通道 {2}:{3} <----> {4}:{5}".format(
            self.socket_map[_cluster["heart_beat_conn"]]["add"][0],
            self.socket_map[_cluster["heart_beat_conn"]]["add"][1],
            self.socket_map[_cluster["server_conn"]]["add"][0],
            self.socket_map[_cluster["server_conn"]]["add"][1],
            self.socket_map[_cluster["client_conn"]]["add"][0],
            self.socket_map[_cluster["client_conn"]]["add"][1])

        print("[INFO] {0} {1}".format(log, "开始服务"))

        connections = [client_conn, forward_conn]
        while True:
            if self.ip_live_map[self.socket_map[_cluster["heart_beat_conn"]]["add"][0]] is False:
                return



            try:
                rs, ws, es = select.select(connections, [], [])
            except:
                forward_conn.close()
                client_conn.close()
                print("[WARN] {0} {1}".format(log, "关闭服务"))
                self.socket_map[_cluster['command_conn']]["conn"].send(bytes('S_RESET', encoding='utf-8'))



            for r in rs:
                if r.fileno() == -1:
                    self.socket_map[_cluster['command_conn']]["conn"].send(bytes('S_RESET', encoding='utf-8'))
                    print("[WARN] {0} {1}".format(log, "异常终止"))
                    return
                try:
                    for r in rs:
                        if r is forward_conn:
                            forward_msg = r.recv(1024)
                            if forward_msg is None:
                                client_conn.close()
                                return
                            else:
                                client_conn.send(forward_msg)
                        else:
                            agent_msg = r.recv(1024)
                            if agent_msg is None:
                                forward_conn.close()
                                return
                            else:
                                forward_conn.send(agent_msg)
                except:
                    forward_conn.close()
                    client_conn.close()
                    print("[WARN] {0} {1}".format(log, "关闭"))
                    self.socket_map[_cluster['command_conn']]["conn"].send(bytes('S_RESET', encoding='utf-8'))
                    return
    # 关闭服务
    def close_connection(self,r):
        print(r)
        _cluster = {}
        if r.fileno() ==-1:

            for key in self.service_cluster:
                if self.socket_map[self.service_cluster[key]["heart_beat_conn"]]["conn"].fileno() == -1:
                    _cluster = self.service_cluster[key]

            for key in _cluster:
                if not key == "heart_beat_listen" and not key == "visit_host_time":
                    self.socket_map[_cluster[key]]["conn"].close()
                    del self.socket_map[_cluster[key]]

            if "heart_beat_conn" in _cluster.keys():
                del self.service_cluster[_cluster["heart_beat_conn"]]
                del self.ip_live_map[_cluster["heart_beat_conn"]]

        else:

            self.ip_live_map_lock.acquire()
            self.ip_live_map[self.socket_map[r.fileno()]["add"][0]] = False
            self.ip_live_map_lock.release()

            self.heart_beat_connections.remove(r)

            _cluster = self.service_cluster[r.fileno()]

            del self.service_cluster[r.fileno()]
            for key in _cluster:
                if not key == "heart_beat_listen" and not key == "visit_host_time":
                    self.socket_map[_cluster[key]]["conn"].close()
                    del self.socket_map[_cluster[key]]

    def thread_heart_beat_guard(self):
        while True:
            ex = []
            for key in self.service_cluster:
                if time.time() - self.service_cluster[key]["visit_host_time"] > 20:
                    self.heart_beat_connections.remove(
                        self.socket_map[self.service_cluster[key]["heart_beat_conn"]]["conn"])
                    self.ip_live_map[self.socket_map[self.service_cluster[key]["heart_beat_conn"]]["add"][0]] = False
                    ex.append(self.service_cluster[key])


            for e in ex:
                print("[INFO] 主机{0}:{1} 退出".format(self.socket_map[e["heart_beat_conn"]]["add"][0],self.socket_map[e["heart_beat_conn"]]["add"][1]))
                del self.service_cluster[e["heart_beat_conn"]]
                for k, v in e.iteritems():
                    self.socket_map[v]["conn"].close()
                    del self.socket_map[v]


            # print("==========调试=============")
            # print(self.socket_map)
            # print(self.ip_live_map)
            # print(self.service_cluster)
            # print("==========调试=============")
            time.sleep(10)


    def start_listen_heart_beat(self):
        self.create_heart_beat_Listen()
        command_listen = None
        print("[INFO] SERVER RUNNING")
        cluster = {}
        heartbeat_count = 0

        _t = threading.Thread(target=self.thread_heart_beat_guard)
        _t.setDaemon(True)
        _t.start()
        self.threads["guard_thread"] = _t



        while True:
            try:
                rs, ws, es = select.select(self.heart_beat_connections, [], [])
            except ValueError:
                pass
            # print(self.heart_beat_connections)
            for r in rs:

                if r is self.heart_beat_listen:

                    cluster['heart_beat_listen'] = self.heart_beat_listen.fileno()
                    heart_beat_conn, heart_beat_add = self.heart_beat_listen.accept()
                    cluster['heart_beat_conn'] = heart_beat_conn.fileno()

                    print("[INFO] CLIENT {0}:{1} join server".format(heart_beat_add[0], heart_beat_add[1]))

                    command_listen = self.create_listen_socket(0)

                    print("[INFO] COMMAND PORT LISTENING:{0}".format(command_listen.getsockname()[1]))

                    cluster['command_listen'] = command_listen.fileno()
                    cluster['visit_host_time'] = time.time()

                    self.service_cluster[heart_beat_conn.fileno()] = cluster

                    # 保存文件描述符
                    self.socket_map_lock.acquire()
                    self.socket_map[heart_beat_conn.fileno()] = {"conn": heart_beat_conn, "add": heart_beat_add}
                    self.socket_map[command_listen.fileno()] = {"conn": command_listen,
                                                                "add": command_listen.getsockname()}
                    self.socket_map_lock.release()

                    # 添加到请求遍历列表中
                    self.heart_beat_connections.append(command_listen)
                    self.heart_beat_connections.append(heart_beat_conn)
                    # ip 存活
                    self.ip_live_map_lock.acquire()
                    self.ip_live_map[heart_beat_add[0]] = True
                    self.ip_live_map_lock.release()

                    # 发送端口信息
                    heart_beat_conn.send(
                        bytes('S_COMM_CONN_PORT:{0}'.format(command_listen.getsockname()[1]), encoding='utf-8'))
                    heartbeat_count += 1

                elif r is command_listen:

                    _cluster = None
                    for key in self.service_cluster:
                        if self.service_cluster[key]["command_listen"] == command_listen.fileno():
                            _cluster = self.service_cluster[key]

                    command_conn, command_add = command_listen.accept()
                    _cluster["command_conn"] = command_conn.fileno()
                    print("[INFO] 主机{0}:{1}命令通道连接成功".format(command_add[0], command_add[1]))

                    self.socket_map_lock.acquire()
                    self.socket_map[command_conn.fileno()] = {"conn": command_conn, "add": command_add}
                    self.socket_map_lock.release()

                    t1 = threading.Thread(target=self.start_command_listening,
                                          args=[command_conn, command_listen, _cluster])
                    t1.setDaemon(True)
                    t1.start()
                    self.threads["server_thread"].append(t1)
                    self.heart_beat_connections.remove(command_listen)

                else:
                    try:
                        if r.fileno() == -1:
                            self.close_connection(r)

                        live_detect_msg = r.recv(1024)
                        if live_detect_msg == bytes('HELLO', encoding='utf-8'):

                            self.service_cluster[r.fileno()]["visit_host_time"] = time.time()

                            self.ip_live_map_lock.acquire()
                            self.ip_live_map[self.socket_map[r.fileno()]["add"][0]] = True
                            self.ip_live_map_lock.release()
                            r.send(bytes('OK', encoding='utf-8'))


                        elif not live_detect_msg:
                            self.close_connection(r)


                    except ConnectionResetError as e:
                        self.close_connection(r)


port_agents = [
    {
        "user": 'xxxxx',
        "delegation_port": 3389,
        "agent_port": 9898,
        "state": 'open'
    }
]

Server(port_agents).start_listen_heart_beat()
