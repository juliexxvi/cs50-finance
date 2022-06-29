import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

BUY_TYPE = "BUY"
SELL_TYPE = "SELL"

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
# export API_KEY=pk_83ddf697a86d4dac80a12f4bbd6c15ab
if not os.environ.get("API_KEY"):
    print(os.environ.keys)
    raise RuntimeError("API_KEY not set")

# the user must log in to actually see this index page
# Index is going to query data from the database and display data about all of the current stocks that the user logged in owns
# We will display a table that shows the values of all the current user's stock, how many shares of each of the stocks they have, total value of each of the holdings which is just the current price of each stock * by the number of shares of each stock
# Run query selecting from the table in buy, all of the stocks that the currently logged in user owns and we can get access to the user by taking a look at the value of session[user ID] to get who is currently logged in
# Then use the look up function to look up the current price of each of those stocks and then we display all of that data inside of some sort of template (index.html)


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks like which stocks the user currently owns and how much each of those stocks it was"""
    holdings_rows = db.execute(
        "SELECT * FROM holdings WHERE shares > 0 AND user_id = ? ORDER BY symbol ASC", session["user_id"])
    rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    cash = rows[0]["cash"]
    total = cash
    for i in range(len(holdings_rows)):
        look_up = lookup(holdings_rows[i]["symbol"])
        holdings_rows[i]["name"] = look_up["name"]
        holdings_rows[i]["price"] = look_up["price"]
        holdings_rows[i]["total"] = look_up["price"] * \
            holdings_rows[i]["shares"]
        total += holdings_rows[i]["total"]
    # holdings la cua jinja
    return render_template("index.html", holdings=holdings_rows, cash=cash, usd=usd, total=total)
    # return apology("TODO") #this displays a to do message to the user if they ever try to visit this page. We can use apology function to return some sort of error message in general

# This is going the function handles displaying a form for the user to type in what stocl they want to buy and also handling the logic of actually purchasing a stock
# Buy stock, we're gonna display some sort of form that let users type in the stock they would like to buy and the number of shares of that stock they would like to buy.
# Similar to quote except to just specifying the name of the stock and they'll alseo specify how many shares of that stock they would like to purchase
# 1. We need to query the database for the current user to make sure the user can afford the current stock, checking the current amount of cash that they have which is store in the user's table and comparing that against the price of the stock which we can look up using lookup function times the number of shares of that stock they want to buy
# 2. If the user is able to afford the stock and the stock exists, we then need to add 1 or more tables to finance database (users) - including users, .. number of shares were bought, who bought, what is the stock


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    if request.method == "POST":
        symbol_code = request.form.get("symbol")
        shares = request.form.get("shares", type=int)
        result = lookup(symbol_code)
        if not symbol_code or not result:
            return apology("symbol is not valid")
        if shares <= 0:
            return apology("share is not valid")
        buy_total = shares * result["price"]

        users = db.execute(
            "SELECT * FROM users WHERE id = ?", session["user_id"])
        if users[0]["cash"] < buy_total:
            return apology("not enough cash")

        current_cash = users[0]["cash"] - buy_total

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transaction_type, date) VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S', datetime('now')))",
                   session["user_id"], symbol_code, shares, result["price"], BUY_TYPE)
        db.execute("UPDATE users SET cash = ? WHERE id = ?",
                   current_cash, session["user_id"])
        symbol_rows = db.execute(
            "SELECT * FROM holdings WHERE user_id = ? AND symbol = ?", session["user_id"], symbol_code)
        if len(symbol_rows) == 0:
            db.execute("INSERT INTO holdings (user_id, symbol, shares) VALUES (?, ?, ?)",
                       session["user_id"], symbol_code, shares)
        else:
            current_shares = symbol_rows[0]["shares"] + shares
            # db.execute("UPDATE holdings SET shares = ? WHERE user_id = ? AND symbol = ?", current_shares, session["user_id"], symbol_code)
            db.execute("UPDATE holdings SET shares = ? WHERE id = ?",
                       current_shares, symbol_rows[0]["id"])
        return redirect("/")


# This is going to display the history of all the transactions
# 1. Querying the table we've already have or we need to create a new table that's keeping track of this information such that when users are buying and selling stocks, we should keep track of when that happened , how many stocks were bought and sold and what stock is
# 2. We display all of that just inside of a table, similar to index (keeps all transactions currently happend) - keeping all the transactions that have ever happened for the user row by row
@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC", session["user_id"])
    return render_template("history.html", transactions=transactions)

# This accepts 2 different methods, GET is used when we just want to get a web page and POST is used if we want to submit data via a form
# When user typed in the username and password and click the log in button, then we're gonna hit the log in route again but this time using a request method of POST meaning sending data that is username and password to the log in route


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST). If the request method if POST, or if the user was trying to submit some data via this form to the log in route, let's try and log the user in
    if request.method == "POST":  # This is when the user hits submit the form

        # Ensure username was submitted - Check for error: request.form is the form that user submitted and if we try and get the input field that had a name of a username.
        if not request.form.get("username"):
            # If not that, we're saying if there was no username typed in, we then return an apology message
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            # Likewise, if the user didnt type in their password then return the message
            return apology("must provide password", 403)

        # Ensure that these are actually valid credentials. To do that we need to connect our controller to the model, we need application.py talk to database finance.db to see if there's user that has this username that is valid
        # Query database for username -> Execute a particular line of SQL
        # Select * from users where username in db = and then colon username means this is a placeholder for a value that we're going to plug in. It's going to be whatever user typed into the form
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          request.form.get("username"))

        # Ensure username exists and password is correct
        # if the length of the row is not 1 that means there is no user with that username or 1 row will come back means there is a user with that username and that's the row was selected
        # Check password hash will check to make sure that this password corresponds to the has value that store in the database (row[0]["hash"])
        # Hash function on the password and get a hash value and then when someone tries to log in, the application will try to hash the password that was typed in and check to ensure that the password hashes match up
        if len(rows) == 0 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid login details")
        # Remember which user has logged in - use Flask session that allows us to store data associated with the user's current interaction with this website
        else:
            session["user_id"] = rows[0]["id"]
        # we're going to store inside of session user's ID a particular value. Then take the 1st row and get the value of ID column for that row
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

# This lets the user look up a particular stock quote
# 1. If user tried to get the quote route, we should display a form that lets user request a stock quote that they would like to look at
# 2. When user submits that form and the for is therefore submitted by a POST, we should look up that stock symbol as by calling the lookup function
# 3. Inside of a file called helpers.py, we can find lookup function that takes as its argument a stock symbol , it then gives us back that data in the form of a python dictionary
# 4. We can print out that dictionary to see what data actually comes back to us after we've looked up the value of a stock so we know how to user that infor to display the current value of stock
# 5. If user types in an invalid symbol that doesn't actually represent a valid stock, lookup is not going to be able to determine what stock we've looking for so it will return the python value none meaning no result came back - > we can user apology message


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    # value = goiUrl("https://cloud.iexapis.com/stable/stock/nflx/quote?token=API_KEY")
    symbol_code = request.form.get("symbol")
    result = lookup(symbol_code)
    result["price"] = usd(result["price"])
    return render_template("quoted.html", data=result)
    # return render_template("quoted.html", name=result["name"], symbol=result["symbol"], price=usd(result["price"]))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user - let the user to register for a page"""
    if request.method == "GET":
        return render_template("register.html")

    if request.method == "POST":
        password = request.form.get("password")
        password_again = request.form.get("password-again")
        username = request.form.get("username")

        if password != password_again:
            return apology("Sorry the passwords do not match")

        users = db.execute(
            "SELECT * FROM users WHERE username = (?)", username)
        if len(users) != 0:
            return apology("Sorry the username is already taken")

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                   username, generate_password_hash(password))
        return redirect("/")

    # 1. When requested via GET, we should just display a form that lets the user register for a new account. It's similar to login.html but need to add a password confirmation field, someplace where the user types in their password again to make sure the passwords match up before let the user register
    # 2. When requested via POST, if the user submitted the register form, then we should register the user as by inserting the new user into the users table.
    # 3. We need to do error checking first. If the user didn't type in a username or if the username they typed in is already th eusername of another user in our database or if the password confirmation field doesn't match the password field then we shoudl display an apology message "Sorry the username is already taken or Sorry your passwords didn't match"
    # 4. Be sure to hash that user's password and store that hash in the database instead because we dont want to store the actual password of the user inside of the database


# 1. When requested by a GET, we should just display a form that lets users indecate what stock they would like to sell and how many shares of that stock they would like to sell
# 2. When the form is submitted voa POST, we can sell that specified number of shares of stock.
# 3. There will have some error conditioning we should do here. We want to check to make sure the user actually owns that stock and they're not trying to sell more shares of stock than they currently own
# 4. But if they are able to sell that stock, we should update the user's cash in order to add to it whatever number of shares of stock they're selling * by the current value of the stock -> we have the current value of the stock using lookup function
# 5. Then make sure to update any of our tables that keeping track of how many shares of stock the user owns in order to indicate that they have sold some number of shares of that stock

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    holdings = db.execute(
        "SELECT * FROM holdings WHERE shares > 0 AND user_id = ?", session["user_id"])
    if request.method == "GET":
        symbols = []
        for holding in holdings:
            symbols.append(holding["symbol"])
        return render_template("sell.html", symbols=symbols)
    if request.method == "POST":
        shares = request.form.get("shares", type=int)
        symbol = request.form.get("symbol")
        found = None
        for holding in holdings:
            if holding["symbol"] == symbol:
                found = holding
                if holding["shares"] < shares:
                    return apology("invalid number of shares")
        if not found:
            return apology("invalid symbol")  # avoid from hacker
        current_shares = found["shares"] - shares
        db.execute("UPDATE holdings SET shares = ? WHERE id = ?",
                   current_shares, found["id"])
        users = db.execute(
            "SELECT * FROM users WHERE id = ?", session["user_id"])
        result = lookup(symbol)
        if not result:
            return apology("symbol is not valid")
        current_cash = users[0]["cash"] + shares * result["price"]
        db.execute("UPDATE users SET cash = ? WHERE id = ?",
                   current_cash, session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transaction_type, date) VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S', datetime('now')))",
                   session["user_id"], symbol, shares, result["price"], SELL_TYPE)
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
