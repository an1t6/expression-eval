def op_priority(op):
    if op in ('+', '-'):
        return 1
    if op in ('*', '/'):
        return 2
    return 0

def infix_to_postfix(expression):
    stack = []
    output = []
    tokens = expression.replace(" ", "")
    i = 0
    
    while i < len(tokens):
        if tokens[i].isdigit():
            num = tokens[i]
            while i + 1 < len(tokens) and tokens[i + 1].isdigit():
                num += tokens[i + 1]
                i += 1
            output.append(num)
        elif tokens[i] in "+-*/":
            while stack and op_priority(stack[-1]) >= op_priority(tokens[i]):
                output.append(stack.pop())
            stack.append(tokens[i])
        i += 1

    while stack:
        output.append(stack.pop())
        
    return output

def postorder_traversal(expression):
    stack = []
    for token in expression:
        if token.isdigit():
            stack.append(float(token))
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
    return stack[0]

def result(filename):
    results = []
    with open(filename, 'r') as file:
        for line in file:
            expression = line.strip()
            if expression:  
                postfix = infix_to_postfix(expression)
                result = postorder_traversal(postfix)
                results.append(result)
    return results

filename = 'C:\\Users\\rkdrl\\Desktop\\HW#3\\expression\\expression1.txt'
results = result(filename)
print(results)
