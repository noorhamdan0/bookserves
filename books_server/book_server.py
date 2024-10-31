# Import necessary modules
import os
from flask import Flask, render_template, request, redirect, url_for, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Float, Integer, String, ForeignKey, or_
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from flask_socketio import SocketIO

# Define a base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Initialize the Flask application and SocketIO
app = Flask(__name__)
socketio = SocketIO(app)

# Configure SQLAlchemy with SQLite
app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///' + os.path.join(os.getcwd(), 'project.db')
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Define SQLAlchemy models for Catalog and Book
class Catalog(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)

class Book(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    count: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Float, default=0)
    catalog_id: Mapped[int] = mapped_column(ForeignKey(Catalog.id))
    catalog: Mapped[Catalog] = relationship(Catalog)

# Create database tables
with app.app_context():
    db.create_all()

# Helper function to log messages
def log(message):
    with open('./catalog_log.txt', 'a') as logger:
        logger.write(f'{message}\n')

# Socket.io event handlers
@socketio.on('catalog_change')
def handle_catalog_change(message):
    catalog_info = message.get('catalog_info')
    if catalog_info:
        key = catalog_info.get('id')
        if key:
            app.logger.info(f"Received catalog change: {catalog_info}")
        else:
            app.logger.warning("No key found in catalog_info")
    else:
        app.logger.warning("No catalog_info found in message")

@socketio.on('book_change')
def handle_book_change(message):
    book_info = message.get('book_info')
    if book_info:
        key = book_info.get('id')
        if key:
            app.logger.info(f"Received book change: {book_info}")
        else:
            app.logger.warning("No key found in book_info")
    else:
        app.logger.warning("No book_info found in message")

@socketio.on('catalog_change_replica')
def handle_catalog_change_replica(message):
    catalog_info = message.get('catalog_info')
    if catalog_info:
        print(f"Received catalog change from Replica: {catalog_info}")
    else:
        app.logger.warning("No catalog_info found in message")

@socketio.on('book_change_replica')
def handle_book_change_replica(message):
    book_info = message.get('book_info')
    if book_info:
        print(f"Received book change from Replica: {book_info}")
    else:
        app.logger.warning("No book_info found in message")

# API Endpoints
@app.get('/catalogs')
def get_all_catalogs():
    """Retrieve all catalogs."""
    try:
        catalogs = db.session.execute(db.select(Catalog).order_by(Catalog.id)).scalars()
        catalogs_list = [{'id': catalog.id, 'name': catalog.name} for catalog in catalogs]
        log(f'make GET request on /catalogs > get all catalogs {datetime.now()}')
        return jsonify({'catalogs': catalogs_list})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)

@app.post('/catalogs')
def create_catalog():
    """Create a new catalog."""
    try:
        name = request.form['name']
        catalog = Catalog(name=name)
        db.session.add(catalog)
        db.session.commit()
        log(f'make POST request on /catalogs > add new catalog {datetime.now()}')
        socketio.emit('catalog_change', {'catalog_info': {'id': catalog.id, 'name': catalog.name}}, namespace='/replica')
        return jsonify({'success': True, 'catalog': catalog.name, 'catalog_id': catalog.id})
    except KeyError:
        return make_response(jsonify({'error': 'no name was provided'}), 400)

@app.get('/books')
def get_all_books():
    """Retrieve all books."""
    try:
        books = db.session.execute(db.select(Book).order_by(Book.id)).scalars()
        books_list = [{'id': book.id, 'name': book.name, 'count': book.count, 'price': book.price} for book in books]
        return jsonify({'books': books_list})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 500)

@app.post('/books')
def create_book():
    """Create a new book."""
    try:
        name = request.form['name']
        catalog = int(request.form['catalog'])
        count = int(request.form['count'])
        price = float(request.form['price'])
        book = Book(name=name, catalog_id=catalog, count=count, price=price)
        db.session.add(book)
        db.session.commit()
        socketio.emit('catalog_change', {'catalog_info': {'id': catalog, 'name': name}}, namespace='/replica')
        socketio.emit('book_change', {'book_info': {'id': book.id, 'name': book.name, 'catalog': book.catalog_id}}, namespace='/replica')
        return jsonify({'success': True, 'book': book.name, 'book_id': book.id})
    except Exception as exc:
        return make_response(jsonify({'error': str(exc)}), 400)

@app.get('/books/search/<string:name>')
def search_books(name):
    """Search for books by name."""
    books = db.session.execute(db.select(Book).filter_by(name=name)).scalars()
    books_list = [{'name': book.name, 'price': book.price, 'id': book.id} for book in books]
    return jsonify({'books': books_list})

@app.get('/books/find')
def get_book_by_name():
    """Get books by name using a search string."""
    search_string = request.args.get('name', '')
    books = db.session.query(Book).filter(or_(Book.name.like(f"%{search_string}%"))).all()
    book_info = [{'id': book.id, 'name': book.name, 'count': book.count} for book in books]
    return jsonify({'books': book_info})

@app.get('/books/<int:id>')
def get_book(id):
    """Retrieve book by ID."""
    try:
        book = Book.query.filter_by(id=id).first()
        book_info = {'id': book.id, 'name': book.name, 'count': book.count}
        return jsonify({'books': book_info})
    except Exception as exc:
        return make_response(jsonify({'error': str(exc)}), 404)

@app.get('/books/<int:id>/stock/availability')
def stock_availability(id):
    """Check stock availability of a book by ID."""
    book = Book.query.filter_by(id=id).first()
    if book.count == 0:
        return make_response(jsonify({'success': False, 'message': 'Out of stock'}), 403)
    return jsonify({'success': True, 'left': book.count})

@app.put('/books/<int:id>/count/increase')
def increase_book_stock(id):
    """Increase the stock count of a book by ID."""
    try:
        book = Book.query.filter_by(id=id).first()
        book.count += 1
        db.session.commit()
        socketio.emit('book_change', {'book_info': {'id': book.id, 'name': book.name, 'catalog': book.catalog_id}}, namespace='/replica')
        return jsonify({'count': book.count})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 404)

@app.put('/books/<int:id>/count/decrease')
def decrease_book_stock(id):
    """Decrease the stock count of a book by ID."""
    try:
        book = Book.query.filter_by(id=id).first()
        book.count -= 1
        db.session.commit()
        socketio.emit('book_change', {'book_info': {'id': book.id, 'name': book.name, 'catalog': book.catalog_id}}, namespace='/replica')
        return jsonify({'count': book.count})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 404)

@app.put('/books/<int:id>/price')
def update_book_price(id):
    """Update the price of a book by ID."""
    try:
        price = float(request.form['price'])
        book = Book.query.filter_by(id=id).first()
        book.price = price
        db.session.commit()
        socketio.emit('book_change', {'book_info': {'id': book.id, 'name': book.name, 'catalog': book.catalog_id}}, namespace='/replica')
        return jsonify({'price': book.price})
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 404)

# Run the Flask application with SocketIO on host 0.0.0.0 and port 4000 in debug mode
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=4000, debug=True)
