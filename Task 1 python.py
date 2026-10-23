import math

num1 = float(input("Enter the first number: "))
operator = input("Enter the operator: ")
num2 = float(input("Enter the second number: "))

if operator == "+":
    result = num1 + num2
elif operator == "-":
    result = num1 - num2
elif operator == "*" or operator == "x" or operator == "X":
    result = num1 * num2
elif operator == "/" or operator == "÷":
    if num2 == 0:
        print("Error: Cannot divide by zero.")
        exit()
    else:
        result = num1 / num2
else:
    print("Error: Invalid operator.")
    exit()

print(num1, operator, num2, "=", result)