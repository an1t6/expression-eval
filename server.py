import logging
import time
import socket
import threading
from queue import Queue
from datetime import datetime

client_status = {} # 클라이언트 상태 추적 변수
start_time = datetime.now() # datetime 라이브러리를 이용한 실행 시간 계산

# ------------ thread safe 방식의 알고리즘 객체 생성 python에서는 queue 또는 priorityQueue 모듈에 있어 thread safe에 대한 락킹 기능을 제공.
task_queue = Queue(maxsize=30)  # queue 모듈.        또한, python에서의 heapq 모듈은 thread safe를 만족하지 않기에 queue를 채택
calculate_thread_lock = threading.Lock()    # threading.lock 라이브러리를 사용한 뮤텍스로 다른 스레드의 인터럽트를 막음
calculate_thread_status = [] # 계산 스레드 상태


logging.basicConfig(filename="Server.txt", level=logging.INFO, filemode='w', encoding='utf-8')

def create_task(client_socket, client_num, expression): # 클라이언트별 작업 수와 총 소요 시간
    if client_num not in client_status:
        client_status[client_num] = {"total_task": 0, "total_time": 0}
    
    return {
        "client_socket": client_socket,     # 사전 라이브러리 기능으로 구현
        "client_num": client_num,
        "expression": expression,
        "op_time": 0 
    }

def waiting_thread(server_socket):   
    while True:                        
        client_socket, client_address = server_socket.accept()
        statsus = client_socket.recv(1024).decode()         # 클라이언트로부터 요청 전송받음
        client_num, expression = statsus.split(":", 1)

        if task_queue.full():      # 큐가 가득 찼다면 작업 거부 전송
            client_socket.send("작업이 거부되었습니다".encode())
            logging.info(f"[{calculate_time}ms] 클라이언트 {client_num}의 작업이 거부되었습니다")
        else:
            _, calculate_time = evaluate_expression(expression)       # 수행 시간 반환 받음. 전방의 _는 결과값이기에 현재 스레드에서는 필요가 없어 공란으로 처리
            task = create_task(client_socket, client_num, expression)
            task['op_time'] = calculate_time
            task_queue.put(task)        #큐에 작업을 집어넣음
            logging.info(f"[{calculate_time}ms] 클라이언트 {client_num}에서 작업 {expression}을 wating 스레드로 전송. 소요된 시간 {calculate_time}ms")

def management_thread(): 
    while True:
        if not task_queue.empty():
            task = task_queue.get()             #taskqueue를 이용해 wating thread에서 대기중인 작업을 get함
            _, calculate_time = evaluate_expression(task['expression'])        # 수행 시간 반환 받음.
            task['op_time'] = calculate_time
            logging.info(f"[{calculate_time}ms] 대기 스레드에서 관리 스레드로 작업 이동: {task['expression']}")
            with calculate_thread_lock: #threading.lock을 이용해 다른 스레드가 동시에 접근하지 못하게 방지
                online_thread = next((t for t in calculate_thread_status if not t['busy']), None) # calculate threads : calculate thread의 상태를 저장. busy가 false인 스레드를 찾는 구문임 즉, 스레드 내의 사용 가능한 스레드를 찾음
                if online_thread:
                    assign_task_to_thread(online_thread, task)     # 스레드가 있다면, assign_task_to_thread를 호출해서 작업을 계산 스레드에 전송
                    logging.info(f"[{calculate_time}ms] 관리 스레드에서 계산 스레드로 작업 이동: {task['expression']}")
                else:
                    logging.info(f"[{calculate_time}ms] 작업 {task['expression']}에 대해 사용 가능한 계산 스레드가 없습니다")
                    
def assign_task_to_thread(statsus, task):  #
    with statsus['condition']:
        statsus['task'] = task  # management thread에서 전송받은 작업 할당
        statsus['busy'] = True  # calculate thread가 사용중인지 아닌지룰 알리는 플래그 개념
        statsus['condition'].notify()   # calculate thread에 신호를 전송

def calculate_thread(statsus):
    while True:
        with statsus['condition']:
            while not statsus['busy']:   # busy 상태가 아닌 경우
                statsus['condition'].wait()   # assign_task_to_thread에서 전송한 notify를 통해 wait 해제
            task = statsus['task']
            if task:
                result, calculate_time = evaluate_expression(task['expression']) # 연산 결과 및 수행 시간 반환 받음
                time.sleep(calculate_time / 1000)       
                client_num = task['client_num']
                client_status[client_num]["total_task"] += 1
                client_status[client_num]["total_time"] += calculate_time
                logging.info(f"[{calculate_time}ms] 클라이언트 {client_num}에 대한 계산 스레드에서 작업 완료: {task['expression']} = {round(result, 1)}")
                task['client_socket'].send(str(round(result, 1)).encode())
                task['client_socket'].close()                               # 작업 결과 전송 및 소켓 종료
                
                logging.info(f"클라이언트 {client_num}의 총 작업 수: {client_status[client_num]['total_task']}, 총 소요 시간: {client_status[client_num]['total_time']}ms")   # 클라이언트 작업 정보 출력
                
                statsus['busy'] = False

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
    calculate_time = leaf_node * 1  # 리프 노드 수 계산
    return result, calculate_time

def start_server(host, port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(5)
    logging.info("서버가 시작되었습니다.")

    threading.Thread(target=waiting_thread, args=(server_socket,)).start()
    threading.Thread(target=management_thread).start()

    for _ in range(200):
        condition = threading.Condition()
        statsus = {
            'busy': False,
            'task': None,
            'condition': condition
        }
        run_calculate_thread = threading.Thread(target=calculate_thread, args=(statsus,))
        calculate_thread_status.append(statsus)
        run_calculate_thread.start()

if __name__ == "__main__":
    start_server("0.0.0.0", 9999)
