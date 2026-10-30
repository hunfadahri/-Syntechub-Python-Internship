import json
import os


class Book:
  

    def __init__(self, book_id, title, author, issued=False):
        self.book_id = str(book_id).strip()
        self.title = str(title).strip()
        self.author = str(author).strip()
        self.issued = bool(issued)

    def to_dict(self):
        return {"id": self.book_id, "title": self.title,
                "author": self.author, "issued": self.issued}

    @classmethod
    def from_dict(cls, d):
        return cls(d["id"], d["title"], d["author"], d.get("issued", False))

    def __str__(self):
        status = "Issued" if self.issued else "Available"
        return f"{self.book_id:<8}{self.title:<30}{self.author:<22}{status:<10}"


class Library:
   
    def __init__(self, filename="library.json"):
        self.filename = filename
        self._books = {}  # book_id -> Book
        self._load()

    def _load(self):
        if not os.path.exists(self.filename):
            return
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    book = Book.from_dict(item)
                    self._books[book.book_id] = book
        except (json.JSONDecodeError, KeyError):
            print(f"Warning: could not read '{self.filename}'. Starting empty.")

    def _save(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump([b.to_dict() for b in self._books.values()], f, indent=2)

   
    def add_book(self, book_id, title, author):
        if not (book_id.strip() and title.strip() and author.strip()):
            raise ValueError("ID, title and author cannot be empty.")
        if book_id.strip() in self._books:
            raise ValueError(f"Book ID '{book_id.strip()}' already exists.")
        self._books[book_id.strip()] = Book(book_id, title, author)
        self._save()

    def search(self, keyword):
        """Case-insensitive match against title or author."""
        kw = keyword.strip().lower()
        return [b for b in self._books.values()
                if kw in b.title.lower() or kw in b.author.lower()]

    def issue_book(self, book_id):
        book = self._get(book_id)
        if book.issued:
            raise ValueError(f"'{book.title}' is already issued.")
        book.issued = True
        self._save()

    def return_book(self, book_id):
        book = self._get(book_id)
        if not book.issued:
            raise ValueError(f"'{book.title}' is not currently issued.")
        book.issued = False
        self._save()

    def list_books(self):
        return sorted(self._books.values(), key=lambda b: b.book_id)

    def report(self):
        total = len(self._books)
        issued = sum(1 for b in self._books.values() if b.issued)
        return {"total": total, "issued": issued, "available": total - issued}

    def _get(self, book_id):
        book = self._books.get(book_id.strip())
        if book is None:
            raise KeyError(f"No book with ID '{book_id.strip()}'.")
        return book



def print_books(books):
    if not books:
        print("\nNo books found.")
        return
    header = f"{'ID':<8}{'Title':<30}{'Author':<22}{'Status':<10}"
    print("\n" + header)
    print("-" * len(header))
    for b in books:
        print(b)
    print("-" * len(header))


def print_report(r):
    print("\n--- Library Report ---")
    print(f"Total books : {r['total']}")
    print(f"Issued      : {r['issued']}")
    print(f"Available   : {r['available']}")


def menu():
    print("\n=== Library Book Inventory ===")
    print("1. Add book")
    print("2. Search (title/author)")
    print("3. Issue book")
    print("4. Return book")
    print("5. List all books")
    print("6. Report")
    print("7. Exit")
    return input("Choose an option: ").strip()


def main():
    lib = Library()
    while True:
        choice = menu()
        try:
            if choice == "1":
                lib.add_book(input("ID: "), input("Title: "), input("Author: "))
                print("Book added.")
            elif choice == "2":
                print_books(lib.search(input("Search keyword: ")))
            elif choice == "3":
                lib.issue_book(input("Book ID to issue: "))
                print("Book issued.")
            elif choice == "4":
                lib.return_book(input("Book ID to return: "))
                print("Book returned.")
            elif choice == "5":
                print_books(lib.list_books())
            elif choice == "6":
                print_report(lib.report())
            elif choice == "7":
                print("Goodbye!")
                break
            else:
                print("Invalid option, try again.")
        except (ValueError, KeyError) as e:
            print(f"Error: {e.args[0]}")


if __name__ == "__main__":
    main()
