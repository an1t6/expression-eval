import logging
import time
import socket
import threading
from datetime import datetime

start_time = datetime.now()

def setup_logging(client_num):
    logger = logging.getLogger(f"Client{client_num}")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(f"Client{client_num}.txt", mode='w', encoding='utf-8')
    logger.addHandler(handler)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    
    return logger

def load_expressions(expression_file):
    with open(expression_file, 'r', encoding='utf-8') as f:
        return f.read().splitlines()

def get_system_time():
    return (datetime.now() - start_time).total_seconds() * 1000    

def send_task(server_host, server_port, client_num, expression, logger):
    start_time = get_system_time()  # 작업 전송 시작 시간 기록
    send_time = round(start_time + 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.connect((server_host, server_port))
        message = f"{client_num}:{expression}"
        logger.info(f"[System Clock : {round(start_time, 1)}ms] [클라이언트 {client_num}] 서버에 작업 {expression} 처리를 요청. 소요된 시간 1ms")
        client_socket.send(message.encode())
        response = client_socket.recv(1024).decode()
        wait_time = round(get_system_time() - start_time, 1)  # 응답 대기 시간 계산
        
        return response, send_time, wait_time

def receive_task(server_host, server_port, expression_file, client_num):
    task = load_expressions(expression_file)
    re_task = []
    re_count = 0
    total_wait_time = 0
    logger = setup_logging(client_num)

    for expression in task:
        if expression in re_task:
            re_task.remove(expression)
    
        response, send_time, wait_time = send_task(server_host, server_port, client_num, expression, logger) # send_task에서 전송 시간과 대기 시간 반환
        
        if response == "작업이 거부되었습니다":
            logger.info(f"[System Clock : {round(get_system_time(), 1)}ms] 서버가 클라이언트 {client_num}의 작업을 거부했습니다: {expression}")
            re_task.append(expression)
            re_count += 1
        else:
            total_wait_time += wait_time
            logger.info(f"[System Clock : {send_time}ms] [클라이언트 {client_num}] 서버로부터 요청된 작업 {expression} = {round(float(response), 1)} 전송 받음. 대기한 시간 {wait_time}")
        time.sleep(0.001)

    for expression in re_task:
        response, send_time, wait_time = send_task(server_host, server_port, client_num, expression, logger)
        total_wait_time += wait_time
        logger.info(f"[System Clock : {send_time}ms] 클라이언트 {client_num}에서 거부된 작업 재처리 완료: {expression} = {round(float(response), 1)}")

    total_task = len(task)
    avg_wait_time = round(total_wait_time / total_task, 1) if total_task > 0 else 0
    logger.info(f"클라이언트 {client_num} - 총 작업 수: {total_task}, 평균 대기 시간: {avg_wait_time} ms, 거부된 작업 수: {re_count}")
    print(f"클라이언트 {client_num} - 총 작업 수: {total_task}, 평균 대기 시간: {avg_wait_time} ms, 거부된 작업 수: {re_count}")

def run_clinet(server_host, server_port, expression_file):
    client_threads = []
    
    for i in range(4):
        client_num = i + 1
        client_thread = threading.Thread(target=receive_task, args=(server_host, server_port, expression_file[i], client_num))
        client_thread.start()
        client_threads.append(client_thread)

    for client_thread in client_threads:
        client_thread.join()

if __name__ == "__main__":
    expression_file = [
        "C:\\Users\\rkdrl\\Desktop\\HW#3\\expression\\expression1.txt",
        "C:\\Users\\rkdrl\\Desktop\\HW#3\\expression\\expression2.txt",
        "C:\\Users\\rkdrl\\Desktop\\HW#3\\expression\\expression3.txt",
        "C:\\Users\\rkdrl\\Desktop\\HW#3\\expression\\expression4.txt"
    ]
    run_clinet("127.0.0.1", 9999, expression_file)
