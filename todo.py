def add_task():
 task =input("Enter a new Task: ")
 tasks.append(task)
print("Task added succcessfully! ")




def view_tasks():
 pass
 if len(tasks) == 0:
     print("No tasks available.")
 else:
     print("List of Tasks:")
     for i, task in enumerate(tasks):
         print(f"{i}. {task}")

def delete_tasks():
    if len(tasks) == 0:
     print("No tasks To delete.")
    else:
     print("List of Tasks:")
     for i, task in enumerate(tasks):
         print(f"{i}. {task}")
         choice = int(input("Enter the index of the task to delete: "))
    if 0 < choice <= len(tasks):
                del tasks[choice-1]
                print("Task deleted successfully.")
    else:
        print("Invalid task number!")

def main():
 while True:
     print("\n======== To-Do List Application ========")
 print("1. Add Task")
print("2. View Tasks")
print("3. Delete Task")
print("4. Exit")
input_choice = input("Enter your choice (1-4): ")
if input_choice == '1':
            add_task()
elif input_choice == '2':
            view_tasks() 
elif input_choice == '3':
            delete_tasks()
elif input_choice == '4':
    print("Exiting the application. Goodbye!")
else:
      print("Invalid choice! Please try again.")

if __name__ == "__main__":
                main()

     
     
