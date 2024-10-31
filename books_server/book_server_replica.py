import os
from datetime import datetime
from flask import Flask, jsonify, make_response, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy import Float, Integer, String, ForeignKey, or_
from flask_socketio import SocketIO
from book_server import Book

# Setup SQLAlchemy base and Flask app
Base = declarative_base()
app_replica = Flask(__name__)
socketio_replica = SocketIO(app_replica, cors_allowed_origins="*")

# App configuration
app_replica.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///' + os.path.join(os.getcwd(), 'project_replica.db')
app_replica.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db_replica = SQLAlchemy(app_replica, model_class=Base)

# Models
class CatalogReplica(db_replica.Model):
    __tablename__ = 'catalog_replica'
    id = db_replica.Column(Integer, primary_key=True)
    name = db_replica.Column(String)

class BookReplica(db_replica.Model):
    __tablename__ = 'book_replica'
    id = db_replica.Column(Integer, primary_key=True)
    name = db_replica.Column(String)
    count = db_replica.Column(Integer, default=1)
    price = db_replica.Column(Float, default=0)
    catalog_id = db_replica.Column(Integer, ForeignKey(CatalogReplica.id))
    catalog = relationship(CatalogReplica)

# Create tables
with app_replica.app_context():
    db_replica.create_all()

# Helper functions
data_copy_done = False
def copy_data_from_original_to_replica():
    try:
        global data_copy_done
        if not data_copy_done:
            with app_replica.app_context():
                books_original = Book.query.all()
                for book_original in books_original:
                    book_replica = BookReplica(
                        id=book_original.id,
                        name=book_original.name,
                        count=book_original.count,
                        price=book_original.price,
                        catalog_id=book_original.catalog_id
                    )
                    db_replica.session.add(book_replica)
                    db_replica.session.commit()
                data_copy_done = True
        return True
    except Exception:
        return False

@app_replica.before_request
def before_request():
    with app_replica.app_context():
        copy_data_from_original_to_replica()

# Socket.IO Event Handlers
@socketio_replica.on('catalog_change_replica')
def handle_catalog_change_replica(message):
    catalog_info = message.get('catalog_info')
    if catalog_info:
        print(f"Received catalog change in Replica: {catalog_info}")

@socketio_replica.on('book_change_replica')
def handle_book_change_replica(message):
    book_info = message.get('book_info')
    if book_info:
        print(f"Received book change in Replica: {book_info}")

@socketio_replica.on('catalog_change')
def handle_catalog_change_origin(message):
    catalog_info = message.get('catalog_info')
    if catalog_info:
        print(f"Received catalog change from Replica to Origin: {catalog_info}")

@socketio_replica.on('book_change')
def handle_book_change_origin(message):
    book_info = message.get('book_info')
    if book_info:
        print(f"Received book change from Replica to Origin: {book_info}")

# Endpoint Routes
@app_replica.route('/catalogs', methods=['GET', 'POST'])
def manage_catalogs_replica():
    if request.method == 'GET':
        try:
            catalogs = db_replica.session.execute(
                db_replica.select(CatalogReplica).order_by(CatalogReplica.id)).scalars()
            catalogs_list = [{'id': catalog.id, 'name': catalog.name} for catalog in catalogs]
            return jsonify({'catalogs': catalogs_list})
        except Exception as e:
            return make_response(jsonify({'error': str(e)}), 500)
    elif request.method == 'POST':
        try:
            name = request.form['name']
            catalog_replica = CatalogReplica(name=name)
            db_replica.session.add(catalog_replica)
            db_replica.session.commit()
            socketio_replica.emit('catalog_change_replica', {'catalog_info': {'id': catalog_replica.id, 'name': catalog_replica.name}})
            return jsonify({'success': True, 'catalog': catalog_replica.name, 'catalog_id': catalog_replica.id})
        except KeyError:
            return make_response(jsonify({'error': 'no name was provided'}), 400)

@app_replica.route('/books', methods=['GET', 'POST'])
def manage_books_replica():
    if request.method == 'GET':
        try:
            books = BookReplica.query.all()
            books_list = [{'id': book.id, 'name': book.name, 'count': book.count, 'price': book.price} for book in books]
            return jsonify({'books': books_list})
        except Exception as e:
            return make_response(jsonify({'error': str(e)}), 500)
    elif request.method == 'POST':
        try:
            name = request.form['name']
            catalog = request.form['catalog']
            count = int(request.form['count'])
            price = float(request.form['price'])
            book_replica = BookReplica(name=name, catalog_id=catalog, count=count, price=price)
            db_replica.session.add(book_replica)
            db_replica.session.commit()
            socketio_replica.emit('book_change_replica', {'book_info': {'id': book_replica.id, 'name': book_replica.name, 'count': book_replica.count}})
            return jsonify({'success': True, 'book': book_replica.name, 'book_id': book_replica.id})
        except KeyError as exc:
            return make_response(jsonify({'error': str(exc)}), 400)

@app_replica.route('/books/search/<string:name>')
def search_books_replica(name):
    books = db_replica.session.execute(
        db_replica.select(BookReplica).filter_by(name=name)).scalars()
    books_list = [{'name': book.name, 'price': book.price, 'id': book.id} for book in books]
    return jsonify({'books': books_list})

@app_replica.route('/books/find')
def get_book_by_name_replica():
    search_string = request.args.get('name', '')
    books = db_replica.session.query(BookReplica).filter(BookReplica.name.like(f"%{search_string}%")).all()
    book_info = [{'id': book.id, 'name': book.name, 'count': book.count} for book in books]
    return jsonify({'books': book_info})

@app_replica.route('/books/<int:id>', methods=['GET', 'PUT'])
def manage_book_replica(id):
    if request.method == 'GET':
        book = BookReplica.query.get(id)
        if book:
            return jsonify({'id': book.id, 'name': book.name, 'count': book.count})
        return make_response(jsonify({'error': 'Book not found'}), 404)
    elif request.method == 'PUT':
        price = float(request.form['price'])
        book = BookReplica.query.get(id)
        if book:
            book.price = price
            db_replica.session.commit()
            socketio_replica.emit('book_change_replica', {'book_info': {'id': book.id, 'name': book.name, 'count': book.count}})
            return jsonify({'price': book.price})
        return make_response(jsonify({'error': 'Book not found'}), 404)

@app_replica.route('/books/<int:id>/count/increase', methods=['PUT'])
def increase_book_stock_replica(id):
    book = BookReplica.query.get(id)
    if book:
        book.count += 1
        db_replica.session.commit()
        socketio_replica.emit('book_change_replica', {'book_info': {'id': book.id, 'name': book.name, 'count': book.count}})
        return jsonify({'count': book.count})
    return make_response(jsonify({'error': 'Book not found'}), 404)

@app_replica.route('/books/<int:id>/count/decrease', methods=['PUT'])
def decrease_book_stock_replica(id):
    book = BookReplica.query.get(id)
    if book:
        if book.count > 0:
            book.count -= 1
            db_replica.session.commit()
            socketio_replica.emit('book_change_replica', {'book_info': {'id': book.id, 'name': book.name, 'count': book.count}})
            return jsonify({'count': book.count})
        return jsonify({'error': 'Book is already out of stock'}), 403
    return make_response(jsonify({'error': 'Book not found'}), 404)

@app_replica.route('/books/<int:id>/stock/availability')
def stock_availability_replica(id):
    book = BookReplica.query.get(id)
    if book:
        if book.count == 0:
            return make_response(jsonify({'success': False, 'message': 'Out of stock'}), 403)
        return jsonify({'success': True, 'left': book.count})
    return make_response(jsonify({'error': 'Book not found'}), 404)

# Run the application
if __name__ == '__main__':
    socketio_replica.run(app_replica, host='0.0.0.0', port=4001, debug=True)
