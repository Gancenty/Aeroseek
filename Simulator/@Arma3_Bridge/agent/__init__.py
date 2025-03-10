import threading
import time
import json
import zmq


class Uav_Query:
    def __init__(self):
        self.inited_uav = []
        self.all_uav_info = None

        self.bridge_sub_port = 11000
        self.recieved_cnt = 0

        self.arma3_sub_socket = dict()
        self.arma3_pub_socket = dict()
        self.arma3_rec_msg = dict()

        self.data_lock = threading.Lock()
        self.init_query()
        self.start_threads()

    def init_query(self):
        context_sub = zmq.Context()
        self.bridge_sub_socket = context_sub.socket(zmq.SUB)
        self.bridge_sub_socket.connect(f"tcp://127.0.0.1:{self.bridge_sub_port}")
        self.bridge_sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        time.sleep(0.1)

    def start_threads(self):
        self.threads = []
        self.threads.extend(
            [
                threading.Thread(target=self.arma3_bridge, daemon=True),
                threading.Thread(target=self.uav_monitor, daemon=True),
            ]
        )
        for thread in self.threads:
            thread.start()

    def arma3_bridge(self):
        while True:
            try:
                while True:
                    message = self.bridge_sub_socket.recv_string(zmq.NOBLOCK)
                    self.recieved_cnt += 1
                    try:
                        self.all_uav_info = json.loads(message)
                        for key, value in self.all_uav_info.items():
                            if key not in self.inited_uav:
                                pub_port = value["pub"]
                                sub_port = value["sub"]
                                self.init_zmq(key, pub_port=pub_port, sub_port=sub_port)
                                with self.data_lock:
                                    self.inited_uav.append(key)
                        return
                    except json.JSONDecodeError as e:
                        pass
            except zmq.Again:
                time.sleep(0.2)

    def get_rec_cnt(self):
        return self.recieved_cnt

    def init_zmq(self, entity_id, pub_port, sub_port):
        context_sub = zmq.Context()
        self.arma3_sub_socket[entity_id] = context_sub.socket(zmq.SUB)
        self.arma3_sub_socket[entity_id].connect(f"tcp://127.0.0.1:{sub_port}")
        self.arma3_sub_socket[entity_id].setsockopt_string(zmq.SUBSCRIBE, "")
        self.arma3_rec_msg[entity_id] = None

        context_pub = zmq.Context()
        self.arma3_pub_socket[entity_id] = context_pub.socket(zmq.PUB)
        self.arma3_pub_socket[entity_id].bind(f"tcp://127.0.0.1:{pub_port}")
        time.sleep(0.1)

    def uav_monitor(self):
        while True:
            with self.data_lock:
                for key in self.inited_uav:
                    sub_socket = self.arma3_sub_socket[key]
                    try:
                        message = sub_socket.recv_string(zmq.NOBLOCK)
                        self.arma3_rec_msg[key] = message.split(":", 1)
                    except zmq.Again:
                        continue
            time.sleep(0.01)


uav_finder = Uav_Query()

context = zmq.Context()
object_port = 5557
com_socket = context.socket(zmq.PUB)
com_socket.bind(f"tcp://127.0.0.1:{object_port}")

context = zmq.Context()
info_port = 5559
info_socket = context.socket(zmq.SUB)
info_socket.connect(f"tcp://127.0.0.1:{info_port}")
info_socket.setsockopt_string(zmq.SUBSCRIBE, "")

context = zmq.Context()
detected_object_port = 5560
detected_object_socket = context.socket(zmq.PUB)
detected_object_socket.bind(f"tcp://127.0.0.1:{detected_object_port}")


def send_message(entity_id: str, message: str):
    """
    ["agent.send_message", ["message"]] call py3_fnc_callExtension;
    """
    global uav_finder
    _entity_name = entity_id
    with uav_finder.data_lock:
        if _entity_name in uav_finder.inited_uav:
            pub_socket = uav_finder.arma3_pub_socket[_entity_name]
            pub_socket.send_string(message)


def read_message(entity_id: str):
    """
    ["agent.read_message", [str _entity]] call py3_fnc_callExtension;
    """
    global uav_finder
    _entity_name = entity_id
    with uav_finder.data_lock:
        if _entity_name in uav_finder.inited_uav:
            message = uav_finder.arma3_rec_msg[entity_id]
            uav_finder.arma3_rec_msg[entity_id] = None
            if message is not None:
                return [message[0], eval(message[1])]
            else:
                return ["Y", [0, 0, 0]]
    return ["N", [0, 0, 0]]


def send_object_message(message):
    """
    ["agent.send_com_message", [message]] call py3_fnc_callExtension;
    """
    message = str(message)
    com_socket.send_string(message)


# uav_id => uav2
def read_info_message():
    """
    ["agent.read_info_message", []] call py3_fnc_callExtension;
    """
    try:
        msg = info_socket.recv_string(zmq.NOBLOCK)
        msg = json.loads(msg)
        action = msg["action"]
        uav_id = "uav" + str(msg["uav_id"])
        # {"action": "obj_pos", "uav_id": uav_id, "position": [pos.x, pos.y, pos.z]}
        if action in ["obj_pos", "lookAt"]:
            return ["Y", uav_id, msg["position"]]
    except zmq.Again:
        return ["N", [0, 0, 0]]


def send_detected_object_message(message):
    """
    ["agent.send_detected_object_message", [message]] call py3_fnc_callExtension;
    """
    # message = str(message)
    detected_object_socket.send_string(message)


# if __name__ == "__main__":
#     rec_cnt = 0
#     last_call_time = time.time()
#     try:
#         while True:
#             send_message("uav1", str([1,[1,2,3],4,5,6]))
#             ans = read_message("uav1")
#             if ans[0] == "target":
#                 rec_cnt += 1
#             now_time = time.time()
#             if now_time - last_call_time >= 1:
#                 print(rec_cnt)
#                 rec_cnt = 0
#                 last_call_time = now_time
#             time.sleep(0.01)
#     except KeyboardInterrupt:
#         print("Exiting...")
