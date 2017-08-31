import random
import time
import os
import subprocess
import MySQLdb

first_names = [line.strip() for line in open('mysql/db_entries/first_names.txt')]
last_names = [line.strip() for line in open('mysql/db_entries/last_names.txt')]
dept_names = [line.strip() for line in open('mysql/db_entries/dept_names.txt')]
titles = [line.strip() for line in open('mysql/db_entries/titles.txt')]

statements = ['select','insert']
database = 'employees'

current_dept_emp=['emp_no','dept_no','from_date','to_date']
departments=['dept_no','dept_name']
dept_emp=['emp_no','dept_no','from_date','to_date']
dept_emp_latest_date=['emp_no','from_date','to_date']
dept_manager=['emp_no','dept_no','from_date','to_date']
employees=['emp_no','birth_date','first_name','last_name','gender','hire_date']
salaries=['emp_no','salary','from_date','to_date']
titles=['emp_no','title','from_date','to_date']

table_cols = [current_dept_emp,departments,dept_emp,dept_emp_latest_date,dept_manager,employees,salaries,titles]
table_names = ['current_dept_emp','departments','dept_emp','dept_emp_latest_date','dept_manager','employees','salaries','titles']

def getRandomEmpNo():
    return random.randint(10001,499999)

def getRandomDeptNo():
    return 'd00' + str(random.randint(1,9))

def getRandomDeptName():
    return random.choice(dept_names)

def getRandomFirstName():
    return random.choice(first_names)

def getRandomLastName():
    return random.choice(last_names)

def getRandomGender():
    return random.choice(['M','F'])

def getRandomTitle():
    return random.choice(titles)

def getRandomFromDate():
    return getRandomDate('1985-01-01','2002-08-01','%Y-%m-%d',random.random())
    
def getRandomToDate():
    return getRandomDate('1985-03-01','9999-01-01','%Y-%m-%d',random.random())

def getRandomBirthDate():
    return getRandomDate('1952-02-01','1965-02-01','%Y-%m-%d',random.random())

def getRandomHireDate():
    return getRandomDate('1985-01-01','2000-01-28','%Y-%m-%d',random.random())

def getRandomSalary():
    return random.randint(38623,158220)

def getRandomDate(start, end, format, rand):
    stime = time.mktime(time.strptime(start, format))
    etime = time.mktime(time.strptime(end, format))

    ptime = stime + rand*(etime - stime)

    return time.strftime(format, time.localtime(ptime))

rand_functions = { 'emp_no': getRandomEmpNo,
                  'dept_no': getRandomDeptNo,
                'dept_name': getRandomDeptName,
               'first_name': getRandomFirstName,
                'last_name': getRandomLastName,
                  'gender' : getRandomGender,
                    'title': getRandomTitle,
                'from_date': getRandomFromDate,
                  'to_date': getRandomToDate,
               'birth_date': getRandomBirthDate,
                'hire_date': getRandomHireDate,
                   'salary': getRandomSalary
}

column_types = { 'emp_no': 'string',
                'dept_no': 'string',
              'dept_name': 'string',
             'first_name':  'string',
              'last_name':  'string',
                'gender' :  'string',
                  'title':  'string',
              'from_date': 'value',
                'to_date': 'value',
             'birth_date': 'value',
              'hire_date': 'value',
                 'salary': 'value'
}


def getRandomQuery():
    query = "select "

    # Choose random table to query
    table = random.randint(0,len(table_cols)-1)

    # Choose random fields from that table to query
    chosen_table_cols = random.sample(table_cols[table],random.randint(1,len(table_cols[table])))

    # Randomly choose whether to include a join
    if random.randint(0,1):
        # If a join is used, fields must also specify the table they're referring to
        joined_chosen_table_cols = [table_names[table] + '.' + s for s in chosen_table_cols]
        query += ", ".join(joined_chosen_table_cols)

        # Choose a random table to join to
        join_table = random.randint(0,len(table_cols)-1)

        # Find field common to both fields that can be joined on
        join_on = list(set(table_cols[table]).intersection(table_cols[join_table]).intersection(['emp_no','dept_no']))

        # Find fields unique to joining field
        join_table_cols = set(table_cols[join_table]) - set(table_cols[table]) # Cols unique to joining table

        # Only join if there are fields to join on and unique fields in joining table
        if join_on and join_table_cols:
            # Choose random fields from the join table to query
            chosen_join_table_cols = random.sample(join_table_cols,random.randint(1,len(join_table_cols)))

            # Prepend the join table to each field
            joined_chosen_join_table_cols = [table_names[join_table] + '.' + s for s in chosen_join_table_cols]
            query += ", " + ", ".join(joined_chosen_join_table_cols)

        query += " from " + database + "." + table_names[table]

        # Finish join only if there are fields to join on and unique fields in joining table
        if join_on and join_table_cols:
            # Choose a field to join on
            chosen_join_on = random.choice(join_on)
            query += " join " + database + "." + table_names[join_table] + " on " + table_names[table] + "." + chosen_join_on + " = " + table_names[join_table] + "." + chosen_join_on
    else:
        # Simple query without join
        query += ", ".join(chosen_table_cols) + " from " + database + "." + table_names[table]

    # Randomly choose whether to include a where clause
    if random.randint(0,1):
        # Choose a random field to 'WHERE' on
        col_name = random.choice(table_cols[table])

        # If field is a string, check for db entries that are equal to a random string
        if column_types[col_name] == 'string':
            query += " where " + table_names[table] + "." + col_name + " = '" + str(rand_functions[col_name]()) + "'"
        # If field if a date or number, check for db entries > or < than a random value
        else:
            operation = random.choice(["<",">"])
            query += " where " + table_names[table] + "." + col_name + " " + operation + " '" + str(rand_functions[col_name]()) + "'"

    query += ";" 
    print query
    return query


# To send many queries asynchronously
FNULL = open(os.devnull, 'w')
users = ["reader"]
while True:
    user = random.choice(users)
    subprocess.Popen(["mysql", "-u" + user,"-p" + user,"-e" + getRandomQuery() + ";"], stdout=FNULL)
    time.sleep(60*random.random())

# To send one query after another synchronously
#db = MySQLdb.connect(user="root",passwd="Password!1")
#cur = db.cursor()
#while True:
#    cur.execute(getRandomQuery())
#db.close()
