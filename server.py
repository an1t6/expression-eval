import logging
import time
import socket
import threading
from queue import Queue
from datetime import datetime

client_status = {} # 클라이언트 상태 추적
start_time = datetime.now() # datetime을 이용한 실행 시간 계산
# ------------ thread safe 방식의 알고리즘 객체 생성 python에서는 queue 또는 priorityQueue 모듈에 있어 thread safe에 대한 락킹 기능을 제공.
task_queue = Queue(maxsize=30)  # queue 모듈.        또한, python에서의 heapq 모듈은 thread safe를 만족하지 않기에 queue를 채택
calculate_thread_lock = threading.Lock()  # threading.lock 라이브러리를 사용한 뮤텍스로 다른 스레드의 인터럽트를 막음
calculate_thread_status = []  # 계산 스레드 상태
# ---- log 함수
def set_log(file):
    logger = logging.getLogger(file)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(file, mode='w', encoding='utf-8') 
    formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
# ---- 로그 출력 함수
def log_print(logger, message):
    logger.info(message)
# ---- system clock 계산 함수
def get_system_clock():
    return round((datetime.now() - start_time).total_seconds() * 1000, 1)

def insert_client(client_socket, client_num, expression): # 클라이언트별 작업 수와 총 소요 시간
    if client_num not in client_status:
        client_status[client_num] = {"total_task": 0, "total_time": 0}
    
    return {
        "client_socket": client_socket,
        "client_num": client_num,
        "expression": expression, # 수식
        "op_time": 0,
        "result": None,       # 계산 결과
        "done": threading.Condition()  # thread safe 알고리즘의 Condition을 이용한 완료 여부
    }

def waiting_thread(server_socket, logger):
    while True:
        client_socket, client_address = server_socket.accept()
        request = client_socket.recv(1024).decode()     # 클라이언트로부터 요청 전송받음
        client_num, expression = request.split(":", 1)

        if task_queue.full():    # 큐가 가득 찼다면 작업 거부 전송
            client_socket.send("작업이 거부되었습니다".encode())
            log_print(logger,f"[System Clock : {get_system_clock()}ms] client {client_num}의 작업이 거부되었습니다")
        else:
            _, calculate_time = postorder_traversal_result(expression)        # 수행 시간 반환 받음. 전방의 _는 결과값이기에 현재 스레드에서는 필요가 없어 공란으로 처리
            task = insert_client(client_socket, client_num, expression)
            task['op_time'] = calculate_time
            task_queue.put(task)      #큐에 작업을 집어넣음
            log_print(logger,f"[System Clock : {get_system_clock()}ms] client {client_num}에서 작업 {expression}을 요청. waiting thread에 할당.")

def management_thread(logger):
    while True:
        if not task_queue.empty():
            task = task_queue.get()          #taskqueue를 이용해 wating thread에서 대기중인 작업을 get함
            _, calculate_time = postorder_traversal_result(task['expression'])      # 수행 시간 반환 받음.
            task['op_time'] = calculate_time
            log_print(logger,f"[System Clock : {get_system_clock()+1}ms] wating thread >> management thread {task['expression']}")

            with calculate_thread_lock:         #threading.lock을 이용해 다른 스레드가 동시에 접근하지 못하게 방지
                online_thread = next((t for t in calculate_thread_status if not t['busy']), None) # calculate thread status : calculate thread의 상태를 저장. busy가 false인 스레드를 찾는 구문임 즉, 스레드 내의 사용 가능한 스레드를 찾음
                if online_thread:
                    assign_task(online_thread, task)      # 스레드가 있다면, assign_task를 호출해서 작업을 calculate thread에 전송
                    log_print(logger,f"[System Clock : {get_system_clock()+2}ms] management thread >> calculate thread {task['expression']}")
                else:
                    log_print(logger,f"[System Clock : {get_system_clock()+2}ms] thread is full!")
            with task['done']: 
                task['done'].wait()  # 계산 완료 notify를 전송받을때까지 wait 상태에 있다가, 전송 받으면 wait을 해제하여 결과 값을 전송받음.
                
            client_socket = task['client_socket']       # 해당 데이터셋을
            client_num = task['client_num']
            result = task['result']
            calculate_time = task['op_time']
            client_socket.send(str(round(result, 1)).encode())  # 클라이언트로 전송
            client_socket.close()  
            # ---------------------------------------- 총 작업 수 및 소요 시간
            client_status[client_num]["total_task"] += 1
            client_status[client_num]["total_time"] += calculate_time
            log_print(logger,f"[System Clock : {get_system_clock()}ms] 연산 작업 완료. client {client_num}으로 전송 : {task['expression']} = {round(result, 1)}, 수행 시간 : {calculate_time}")
            log_print(logger,f"[System Clock : {get_system_clock()}ms] client {client_num}의 총 작업 수 : {client_status[client_num]['total_task']}, 총 수행 시간 : {client_status[client_num]['total_time']}ms, 평균 작업 시간 : {round(client_status[client_num]["total_time"]/client_status[client_num]["total_task"],1)}")

def assign_task(status, task):
    with status['condition']:
        status['task'] = task      # management thread에서 전송받은 작업 할당
        status['busy'] = True      # calculate thread가 사용중인지 아닌지룰 알리는 플래그 개념
        status['condition'].notify()    # calculate thread에 notify 신호 전송

def calculate_thread(status, logger):
    while True:
        with status['condition']:
            while not status['busy']:   # busy 상태가 아닌 경우
                status['condition'].wait()      # assign_task에서 전송한 notify를 통해 wait 해제
            task = status['task']
            if task:
                result, calculate_time = postorder_traversal_result(task['expression'])    # 연산 결과 및 수행 시간 반환 받음
                time.sleep(calculate_time / 1000) 
                task['result'] = result
                with task['done']:  
                    task['done'].notify() # notify를 이용해 management로 결과를 다시 전송
                status['busy'] = False  # 계산 스레드를 대기 상태로 전환
# -------------------------------- parse tree 변환
def op_priority(op):
    if op in ('+', '-'):
        return 1
    if op in ('*', '/'):
        return 2
    return 0
# ----------- 중위 표현식 후위 표현식으로
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
            while stack and op_priority(stack[-1]) >= op_priority(token[i]):
                output.append(stack.pop())
            stack.append(token[i])
        i += 1
    while stack:
        output.append(stack.pop())
    return output
#------------------후위 연산
def postorder_traversal(expression):
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
# ------- 결과
def postorder_traversal_result(expression):
    postfix_expr = infix_to_postfix(expression)
    result, leaf_node = postorder_traversal(postfix_expr)
    calculate_time = leaf_node * 1      # 리프 노드 수 계산 (수식 길이 계산)
    return result, calculate_time

def run_server(host, port):
    logger = set_log("Server.txt")
    log_print(logger,f"[System Clock : {get_system_clock()}ms] 서버가 시작되었습니다.")
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # Socket
    server_socket.bind((host, port))
    server_socket.listen(5)
    
    threading.Thread(target=waiting_thread, args=(server_socket, logger)).start()    #thread
    threading.Thread(target=management_thread, args=(logger,)).start()

    for _ in range(200):
        condition = threading.Condition() # 상태
        status = {                      
            'busy': False,
            'task': None,
            'condition': condition
        }
        run_calculate_thread = threading.Thread(target=calculate_thread, args=(status, logger))
        calculate_thread_status.append(status)
        run_calculate_thread.start()

if __name__ == "__main__":
    run_server("0.0.0.0", 8000)     #0.0.0.0으로 설정해 모든 포트에서 연결이 가능하도록
