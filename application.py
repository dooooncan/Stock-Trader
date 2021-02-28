import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

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
if not os.environ.get("API_KEY"):
    try:
        os.environ["API_KEY"] = 'pk_2f7a7ceee9694875901c41cab01cfee2'
    except:
        raise RuntimeError("API_KEY not set")

#Index function (shows portfolio of stock)
add_rows = []
@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    #Query database for portfolio table
    rows = db.execute("""
        SELECT symbol, SUM(shares) as totalShares
        FROM transactions
        WHERE user_id = :user_id
        GROUP BY symbol
        HAVING totalShares > 0;
    """, user_id=session["user_id"])

    #Initiate holdings list
    holdings = []

    grand_total = 0

    #Loop for number of rows in the portfolio
    for row in rows:
        stock = lookup(row["symbol"])
        holdings.append({
            "symbol": stock["symbol"],
            "name": stock["name"],
            "shares": row["totalShares"],
            "price": usd(stock["price"]),
            "total": usd(stock["price"] * row["totalShares"])
        })

        #Grand total is price * number of shares
        grand_total += stock["price"] * row["totalShares"]

    #Update users cash
    rows = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])
    cash = rows[0]["cash"]
    grand_total += cash

    #Display table with current users stock etc
    return render_template("index.html", holdings = holdings, cash=usd(cash), grand_total=usd(grand_total))

#Buy function
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # Ensure password was submitted
    if request.method == "GET":
        return render_template("buy.html")

    # User reached route via POST
    else:

        # error checking for valid stock input (needs to be whole number) or if theres no input to either form
        if not request.form.get("shares").isdigit():
            return apology("Invalid number of shares", 400)

        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("Missing symbol", 400)

        #convert inputted shares to an integer
        shares = int(request.form.get("shares"))
        if shares is None:
            return apology("Invalid symbol or shares", 400)

        # check to see if correct symbol
        stock = lookup(symbol)
        if stock is None:
            return apology("Must provide existing symbol", 400)

        # query database for user cash
        rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        cash = rows[0]["cash"]

        #update amount of user cash
        updated_cash = cash - shares * stock['price']
        if updated_cash < 0:
            return apology("Insufficient funds")

        #update table with new amount of cash
        db.execute("UPDATE users SET cash=:updated_cash WHERE id=:id",
                    updated_cash=updated_cash,
                    id=session["user_id"])

        #add transaction into transactions table
        db.execute("""
                    INSERT INTO transactions (user_id, symbol, shares, price)
                    VALUES (:user_id, :symbol, :shares, :price)""",
                        user_id=session["user_id"],
                        symbol = stock["symbol"],
                        shares = shares,
                        price = stock["price"])

        #flash an alert when stock is bought
        flash("Shares Bought!")

        #return to index page
        return redirect("/")

#History function
@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    #Query database to show history table
    transactions = db.execute("""
        SELECT symbol, shares, price, transacted
        FROM transactions
        WHERE user_id=:user_id
    """, user_id=session["user_id"])

    #Loop for number of rows required
    for  i in range(len(transactions)):
        transactions[i]["price"] = usd(transactions[i]["price"])

    #Return html page
    return render_template("history.html", transactions=transactions)

#Add Cash function
@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add cash to cash reserve"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("add_cash.html")

    # User reached route via POST (as by submitting a form via POST)
    else:

        #When submitted, updates users cash amount
        db.execute("""
            UPDATE users
            SET cash = cash + :amount
            WHERE id=:user_id
        """, amount = request.form.get("cash"),
        user_id = session["user_id"])

        #Flash banner
        flash("Cash Added!")

        return redirect("/")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("login.html")

    # User reached route via POST (as by submitting a form via POST)
    else:

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

#Quote function
@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via GET
    if request.method == "GET":
        return render_template("quote.html")

    # User reached route via POST
    else:

        # Ensure stock form is not empty
        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("Missing symbol", 400)

        # Ensure stock symbol is correct
        stock = lookup(symbol)
        if stock is None:
            return apology("Must provide existing symbol", 400)

        # If symbol is correct then display: A share of (companyName) (symbol) costs (latestprice).
        else:
            return render_template("quoted.html", stock={
                'name': stock['name'],
                'symbol': stock['symbol'],
                'price': usd(stock['price'])
            })

#Register function
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via GET (GET is used to display the form/webpage aka GET the form/webpage) (POST means the user is trying to submit some data)
    if request.method == "GET":
        return render_template("register.html")

    # User reached route via POST
    else:

        # Get inserted info from forms
        username = request.form.get("username")
        password = request.form.get("password")
        pass_confirm = request.form.get("confirmation")
        usernamecheck = db.execute("SELECT COUNT(*) FROM users WHERE username = :username", username=username)

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 400)

        # Ensure username has not already been taken
        elif usernamecheck[0]["COUNT(*)"] != 0:
            return apology("This username has been taken, please use another", 400)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 400)

        # Ensure password was submitted again
        elif not pass_confirm:
            return apology("must provide password again", 400)

        # Ensure passwords match
        elif pass_confirm != password:
            return apology("passwords must match", 400)

        # Hash users password
        hash = generate_password_hash(password)

        # Insert username and hashed password into database
        prim_key = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)

        # rederecting the user to index if success
        return redirect("/")

#Sell function
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    #if requested via GET then return sell.html page with populated Symbols form
    if request.method == "GET":
        rows = db.execute("""
            SELECT symbol
            FROM transactions
            WHERE user_id=:user_id
            GROUP BY symbol
            HAVING SUM(shares) > 0;
        """, user_id=session["user_id"])
        return render_template("sell.html", symbols=[ row["symbol"] for row in rows])

    # User reached route via POST
    else:

        # error checking for valid stock input (needs to be whole number) or if theres no input to either form
        if not request.form.get("shares").isdigit():
            return apology("Invalid number of shares", 403)

        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("Missing symbol", 403)

        #convert inputted shares to an integer
        shares = int(request.form.get("shares"))
        if shares is None:
            return apology("Invalid symbol or shares", 403)

        # check to see if correct symbol
        stock = lookup(symbol)
        if stock is None:
            return apology("Must provide existing symbol", 403)

        #Update table with cahs, sold shares etc
        rows = db.execute("""
            SELECT symbol, SUM(shares) as totalShares
            FROM transactions
            WHERE user_id=:user_id
            GROUP BY symbol
            HAVING totalShares > 0;
        """, user_id=session["user_id"])

        #check to see if there's enough shares to sell
        for row in rows:
            if row["symbol"] == symbol:
                if shares > row["totalShares"]:
                    return apology("Insufficient shares to sell")


        # query database for user cash
        rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        cash = rows[0]["cash"]

        #update amount of user cash
        updated_cash = cash + shares * stock['price']
        if updated_cash < 0:
            return apology("Insufficient funds")

        #update table with new amount of cash
        db.execute("UPDATE users SET cash=:updated_cash WHERE id=:id",
                    updated_cash=updated_cash,
                    id=session["user_id"])

        #add transaction into transactions table
        db.execute("""
                    INSERT INTO transactions (user_id, symbol, shares, price)
                    VALUES (:user_id, :symbol, :shares, :price)""",
                        user_id=session["user_id"],
                        symbol = stock["symbol"],
                        shares = -1 * shares,
                        price = stock["price"])

        #flash an alert when stock is sold
        flash("Shares Sold!")

        #return to index page
        return redirect("/")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
