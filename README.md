# ECO5037S-Q6-Web

## Create a Virtual Environment

In your terminal, navigate to the project directory and create a virtual environment named `venv` by running:
```
python3 -m venv venv
```

This will create a folder named `venv` containing all the necessary files for the virtual environment.

## Activate the Virtual Environment

Once the virtual environment is created, activate it using the appropriate command for your operating system:

- On **macOS/Linux**, run:
```
source venv/bin/activate
```
- On **Windows**, run:
```
.\venv\Scripts\activate
```

## Install Required Dependencies

After activation, install the necessary dependencies by running:
```
pip install -r requirements.txt
```

This will install the Algorand SDK and other required libraries needed for blockchain interactions in the application.

## Running the Application

### Scenario 1: Running the CLI

If you want to run the application via the Command Line Interface (CLI), use the following command:
```
python main.py
```
This will execute the application in CLI mode. You can interact with it via terminal commands, and it will output relevant information directly to your terminal window. This mode is typically used for testing, batch processes, or administrative tasks.

### Scenario 2: Running the Web App

To run the web application, use the following command:
```
python app.py
```

This will launch the web application locally, and you can access it via your web browser at `http://localhost:5000`. In this mode, the application will provide a graphical user interface (GUI) for interacting with the blockchain and other features, making it more user-friendly for general use.
