import json
import os


class Student:
    def __init__(self, student_id, name, grade):
        self.student_id = student_id
        self.name = name
        self.grade = float(grade)

    def to_dict(self):
        return {
            "student_id": self.student_id,
            "name": self.name,
            "grade": self.grade,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(data["student_id"], data["name"], data["grade"])

    def __str__(self):
        return f"{self.student_id:<10}{self.name:<25}{self.grade:>8.2f}"


class StudentManager:
    def __init__(self, filename="students.json"):
        self.filename = filename
        self.students = {}
        self.load()

    def load(self):
        if not os.path.exists(self.filename):
            return

        try:
            with open(self.filename, "r", encoding="utf-8") as file:
                for item in json.load(file):
                    student = Student.from_dict(item)
                    self.students[student.student_id] = student
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            print(f"Warning: could not read '{self.filename}'. Starting empty.")

    def save(self):
        with open(self.filename, "w", encoding="utf-8") as file:
            json.dump(
                [student.to_dict() for student in self.students.values()],
                file,
                indent=2,
            )

    @staticmethod
    def validate(student_id, name, grade):
        if not student_id.strip():
            raise ValueError("ID cannot be empty.")
        if not name.strip():
            raise ValueError("Name cannot be empty.")

        try:
            numeric_grade = float(grade)
        except (TypeError, ValueError) as error:
            raise ValueError("Grade must be a number.") from error

        if not 0 <= numeric_grade <= 100:
            raise ValueError("Grade must be between 0 and 100.")
        return numeric_grade

    def add_student(self, student_id, name, grade):
        numeric_grade = self.validate(student_id, name, grade)
        if student_id in self.students:
            raise ValueError(f"Student with ID '{student_id}' already exists.")

        self.students[student_id] = Student(student_id, name, numeric_grade)
        self.save()

    def update_student(self, student_id, name=None, grade=None):
        if student_id not in self.students:
            raise ValueError(f"No student with ID '{student_id}' found.")

        student = self.students[student_id]
        if name is not None:
            if not name.strip():
                raise ValueError("Name cannot be empty.")
            student.name = name
        if grade is not None:
            student.grade = self.validate(student_id, student.name, grade)
        self.save()

    def delete_student(self, student_id):
        if student_id not in self.students:
            raise ValueError(f"No student with ID '{student_id}' found.")
        del self.students[student_id]
        self.save()

    def list_students(self):
        return list(self.students.values())

    def print_table(self):
        print(f"{'ID':<10}{'Name':<25}{'Grade':>8}")
        print("-" * 43)
        for student in self.students.values():
            print(student)


def menu():
    print("\n=== Student Management System ===")
    print("1. Add student")
    print("2. Update student")
    print("3. Delete student")
    print("4. List students")
    print("5. Exit")
    return input("Enter your choice (1-5): ")


def main():
    manager = StudentManager()
    while True:
        choice = menu()
        if choice == "1":
            student_id = input("Enter student ID: ")
            name = input("Enter student name: ")
            grade = input("Enter student grade: ")
            try:
                manager.add_student(student_id, name, grade)
                print("Student added successfully.")
            except ValueError as error:
                print(f"Error: {error}")
        elif choice == "2":
            student_id = input("Enter student ID to update: ")
            name = input("Enter new name (leave blank to keep current): ")
            grade = input("Enter new grade (leave blank to keep current): ")
            try:
                manager.update_student(
                    student_id,
                    name if name else None,
                    grade if grade else None,
                )
                print("Student updated successfully.")
            except ValueError as error:
                print(f"Error: {error}")
        elif choice == "3":
            student_id = input("Enter student ID to delete: ")
            try:
                manager.delete_student(student_id)
                print("Student deleted successfully.")
            except ValueError as error:
                print(f"Error: {error}")
        elif choice == "4":
            if not manager.list_students():
                print("No students found.")
            else:
                manager.print_table()
        elif choice == "5":
            print("Exiting the application. Goodbye!")
            break
        else:
            print("Invalid choice! Please try again.")


if __name__ == "__main__":
    main()
