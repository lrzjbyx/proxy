import socket
import time
import select
import threading
import copy


class Client():

    def __init__(self, delegation_ip, agent_port, heart_beat_port):
        # 委托 ip
        self.delegation_ip = delegation_ip
        # 代理端口
        self.agent_port = agent_port
        # 心跳检测端口
        self.heart_beat_port = heart_beat_port
        # 心跳连接
        self.heart_beat_conn = None
        # 命令连接
        self.command_conn = None
        # 主机是否存活
        self.delegation_host_live = True
        # 命令端口
        self.command_port = None
        # 映射端口
        self.forward_port = None
        # 映射连接
        self.forward_conn = None
        # 代理
        self.agent_conn = None
        # 状态
        self.conn_state = True
        # 线程连接
        self.threads = {"command_thread": None, "forward_thread": None}
        # 本次访问时间
        self.cur_visit_host_time = None

    def close_connection(self):
        self.heart_beat_conn.close()
        self.forward_conn.close()
        self.agent_conn.close()
        self.command_conn.close()

    def create_conn(self, ip, port):
        _conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        try:
            _conn.connect((ip, port))
        except ConnectionRefusedError:
            return None

        return _conn

    def start_forward_agent(self):
        connections = [self.forward_conn, self.agent_conn]
        # print(connections)
        while True:
            rs, ws, es = select.select(connections, [], [])
            if not self.delegation_host_live:
                print("[INFO] 委托主机出现异常")
                return
            for r in rs:
                try:
                    if r is self.forward_conn:
                        try:
                            forward_msg = r.recv(1024)
                        except ConnectionResetError:
                            self.delegation_host_live = False
                            return

                        if forward_msg is None:
                            self.agent_conn.close()
                            return
                        else:
                            self.agent_conn.send(forward_msg)
                    else:
                        try:
                            agent_msg = r.recv(1024)
                        except ConnectionResetError:
                            self.delegation_host_live = False
                            return
                        if agent_msg is None:
                            self.forward_conn.close()
                            return
                        else:
                            self.forward_conn.send(agent_msg)
                except :
                    self.forward_conn.close()
                    self.agent_conn.close()
                    return


    def start_command_conn(self):

        connections = [self.command_conn]
        while True:
            rs, ws, es = select.select(connections, [], [])
            for r in rs:
                if not self.delegation_host_live:
                    print("[INFO] 委托主机出现异常")
                    return

                if r is self.command_conn:
                    try:
                        command_msg = r.recv(1024)
                    except ConnectionResetError:
                        self.delegation_host_live = False
                        return

                    if command_msg is None:
                        self.heart_beat_conn.close()
                        return
                    # print(command_msg)
                    if bytes('S_MAP_CONN', encoding='utf-8') in command_msg:

                        self.forward_port = int(command_msg.decode(encoding='utf-8').split(":")[1])
                        if (self.forward_conn is None and self.agent_conn is None) or (
                                self.forward_conn.fileno() == -1 and self.agent_conn.fileno() == -1):

                            self.forward_conn = self.create_conn(self.delegation_ip, self.forward_port)

                            self.agent_conn = self.create_conn('127.0.0.1', self.agent_port)

                            print("[INFO] {0}:{1} <----> {2}:{3} 传输通道连接成功".format(self.agent_conn.getsockname()[0],
                                                                   self.agent_conn.getsockname()[1],self.forward_conn.getsockname()[0],self.forward_conn.getsockname()[1]))


                            if self.forward_conn is None or self.forward_conn is None:
                                print("[INFO] 目标主机拒绝连接")
                                return

                            t1 = threading.Thread(target=self.start_forward_agent)
                            t1.setDaemon(True)
                            t1.start()
                            self.threads["forward_thread"] = t1


                    elif bytes('S_RESET', encoding='utf-8') == command_msg:
                        self.agent_conn.close()
                        self.forward_conn.close()

                        self.command_conn.send(bytes('C_RESET', encoding='utf-8'))


                    elif bytes('S_RECONN', encoding='utf-8') == command_msg:
                        self.forward_conn.close()
                        self.agent_conn.close()
                        self.command_conn.close()

                    elif bytes('S_KEY', encoding='utf-8') == command_msg:
                        pass

    def thread_heart_beat_guard(self):
        while True:

            if not self.cur_visit_host_time is None:
                if time.time() - self.cur_visit_host_time >  20:
                    self.delegation_host_live = False

            if self.delegation_host_live is False:
                self.close_connection()
                print("[INFO] 关闭服务")
                return

            time.sleep(3)

    def start_heart_beat_conn(self):
        self.heart_beat_conn = self.create_conn(self.delegation_ip, self.heart_beat_port)
        if self.heart_beat_conn is None:
            print("[INFO] 委托主机拒绝连接")
            return

        print("[INFO] {0}:{1} 委托主机连接成功".format(self.heart_beat_conn.getsockname()[0],self.heart_beat_conn.getsockname()[1]))

        _t = threading.Thread(target=self.thread_heart_beat_guard)
        _t.setDaemon(True)
        _t.start()
        self.threads["guard_thread"] = _t

        connections = [self.heart_beat_conn]
        while True:
            try:
                rs, ws, es = select.select(connections, [], [])
            except ValueError:
                self.delegation_host_live = False
                return


            for r in rs:
                if r is self.heart_beat_conn:
                    heat_beat_msg = r.recv(1024)

                    if heat_beat_msg is None:
                        self.heart_beat_conn.close()
                        self.delegation_host_live = False

                    if bytes('S_COMM_CONN_PORT', encoding='utf-8') in heat_beat_msg:
                        if self.command_conn is None or self.command_conn.fileno() == -1:
                            self.command_port = int(heat_beat_msg.decode(encoding='utf-8').split(":")[1])
                            self.command_conn = self.create_conn(self.delegation_ip, self.command_port)
                            if self.command_conn is None:
                                print("[INFO] 委托主机拒绝连接")
                                continue

                            print("[INFO] {0}:{1} 命令通道连接成功".format(self.command_conn.getsockname()[0],
                                                                   self.command_conn.getsockname()[1]))
                            t1 = threading.Thread(target=self.start_command_conn)
                            t1.setDaemon(True)
                            t1.start()

                            self.threads["command_thread"] = t1

                            self.heart_beat_conn.send(bytes('HELLO', encoding='utf-8'))
                            self.command_conn.send(bytes('DELEGATION:{0}'.format(self.agent_port), encoding='utf-8'))


                    elif bytes('OK', encoding='utf-8') == heat_beat_msg:
                        self.heart_beat_conn.send(bytes('HELLO', encoding='utf-8'))
                        time.sleep(1)
                        self.delegation_host_live = True
                        self.cur_visit_host_time = time.time()




class ManageClient():
    def __init__(self,delegation_ip,agent_port,heart_beat_port):
        self.delegation_ip = delegation_ip
        self.agent_port = agent_port
        self.heart_beat_port = heart_beat_port
        self.client = Client(self.delegation_ip, self.agent_port, self.heart_beat_port)
        self.awake_time_second = 10

    def run(self):
        count = 1
        while True:
            try:
                self.client.start_heart_beat_conn()
            except:
                self.client = Client(self.delegation_ip, self.agent_port, self.heart_beat_port)

            time.sleep(self.awake_time_second)
            print("[INFO] 主机正在进行{0}次重连尝试".format(count))
            count+=1


ManageClient("127.0.0.1", 3389, 9999).run()