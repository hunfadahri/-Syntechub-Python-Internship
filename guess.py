import random
num = random.randint(1,100)
print("Computer selected a number from 1 to 100 (inclusive), now is your turn - ")
turns=0
while True:
    guess=int(input("Enter the guess number:"))
    if (guess==num):
        print("you got it right")
        break
    elif (guess<num):
        print("Bigger number please")
        turns += 1
    elif (guess>num):
         print("smaller number please")
    turns += 1
print("Number of turns = ", turns+1)

