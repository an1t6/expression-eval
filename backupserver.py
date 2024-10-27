import logging
import time
import socket
import threading
from queue import Queue
from datetime import datetime

task_queue = Queue(maxsize=30)
status = {}
calculate_threads = []
calculate_thread_lock = threading.Lock()
start_time = datetime.now()

logging.basicConfig(filename="Server.txt", level=logging.INFO, filemode='w', encoding='utf-8')

def create_task(client_socket, client_num, expression):
    # 클라이언트별 작업 수와 총 소요 시간 초기화
    if client_num not in status:
        status[client_num] = {"total_task": 0, "total_time": 0}
    
    return {
        "client_socket": client_socket,
        "client_num": client_num,
        "expression": expression,
        "op_time": 0  # 실제 수행 시간으로 갱신됨
    }

def waiting_thread(server_socket):
    while True:
        client_socket, client_address = server_socket.accept()
        request = client_socket.recv(1024).decode()
        client_num, expression = request.split(":", 1)

        if task_queue.full():
            client_socket.send("작업이 거부되었습니다".encode())
            logging.info(f"[{exec_time}ms] 클라이언트 {client_num}의 작업이 거부되었습니다")
        else:
            _, exec_time = evaluate_expression(expression)  # 리프 노드 개수만큼의 수행 시간
            task = create_task(client_socket, client_num, expression)
            task['op_time'] = exec_time
            task_queue.put(task)
            logging.info(f"[{exec_time}ms] 클라이언트 {client_num}에서 작업 수신: {expression} -> 대기 스레드")

def management_thread():
    while True:
        if not task_queue.empty():
            task = task_queue.get()
            _, exec_time = evaluate_expression(task['expression'])
            task['op_time'] = exec_time
            logging.info(f"[{exec_time}ms] 대기 스레드에서 관리 스레드로 작업 이동: {task['expression']}")
            with calculate_thread_lock:
                online_thread = next((t for t in calculate_threads if not t['is_busy']), None)
                if online_thread:
                    assign_task_to_thread(online_thread, task)
                    logging.info(f"[{exec_time}ms] 관리 스레드에서 계산 스레드로 작업 이동: {task['expression']}")
                else:
                    logging.info(f"[{exec_time}ms] 작업 {task['expression']}에 대해 사용 가능한 계산 스레드가 없습니다")

def calculate_thread(request):
    while True:
        with request['condition']:
            while not request['is_busy']:
                request['condition'].wait()
            task = request['task']
            if task:
                result, exec_time = evaluate_expression(task['expression'])
                time.sleep(exec_time / 1000)        #작업수행시간
                client_num = task['client_num']
                status[client_num]["total_task"] += 1
                status[client_num]["total_time"] += exec_time

                logging.info(f"[{exec_time}ms] 클라이언트 {client_num}에 대한 계산 스레드에서 작업 완료: {task['expression']} = {round(result, 1)}")
                
                task['client_socket'].send(str(round(result, 1)).encode())
                task['client_socket'].close()                               # 작업 결과 전송 및 소켓 종료
                
                # 클라이언트 작업 정보 출력
                logging.info(f"클라이언트 {client_num}의 총 작업 수: {status[client_num]['total_task']}, 총 소요 시간: {status[client_num]['total_time']}ms")
                
                request['is_busy'] = False

def assign_task_to_thread(request, task):
    with request['condition']:
        request['task'] = task
        request['is_busy'] = True
        request['condition'].notify()

def precedence(op):
    if op in ('+', '-'):
        return 1
    if op in ('*', '/'):
        return 2
    return 0

def infix_to_postfix(expression):
    stack = []
    output = []
    token = expression.replace(" ", "")
    i = 0
    
    while i < len(token):
        if token[i].isdigit():
            num = token[i]
            while i + 1 < len(token) and token[i + 1].isdigit():
                num += token[i + 1]
                i += 1
            output.append(num)
        elif token[i] in "+-*/":
            while stack and precedence(stack[-1]) >= precedence(token[i]):
                output.append(stack.pop())
            stack.append(token[i])
        i += 1

    while stack:
        output.append(stack.pop())
        
    return output

def evaluate_postfix(expression):
    stack = []
    leaf_node = 0
    for token in expression:
        if token.isdigit():
            stack.append(float(token))
            leaf_node += 1
        else:
            right = stack.pop()
            left = stack.pop()
            if token == '+':
                stack.append(left + right)
            elif token == '-':
                stack.append(left - right)
            elif token == '*':
                stack.append(left * right)
            elif token == '/':
                stack.append(left / right)
    return stack[0], leaf_node

def evaluate_expression(expression):
    postfix_expr = infix_to_postfix(expression)
    result, leaf_node = evaluate_postfix(postfix_expr)
    exec_time = leaf_node * 1  # 리프 노드 수가 곧 실행 시간(ms 단위)
    return result, exec_time

def start_server(host, port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(5)
    logging.info("서버가 시작되었습니다.")

    threading.Thread(target=waiting_thread, args=(server_socket,)).start()
    threading.Thread(target=management_thread).start()

    for _ in range(200):
        condition = threading.Condition()
        request = {
            'is_busy': False,
            'task': None,
            'condition': condition
        }
        run_calculate_thread = threading.Thread(target=calculate_thread, args=(request,))
        calculate_threads.append(request)
        run_calculate_thread.start()

if __name__ == "__main__":
    start_server("0.0.0.0", 9999)
