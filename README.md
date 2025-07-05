# Spendie

Spendie is a Python-based expense tracking and management application designed to help individuals and small teams efficiently monitor, categorize, and analyze their spending habits. With an intuitive interface and robust features, Spendie empowers users to take control of their finances, gain insights, and make informed budgeting decisions.

## Features

- **Add and Manage Expenses:** Record daily expenses with categories, amounts, dates, and descriptions.
- **Expense Categories:** Organize spending with customizable categories (e.g., Food, Transport, Utilities, Entertainment).
- **Expense Reports & Analytics:** Visualize spending patterns with monthly/weekly breakdowns and simple charts.
- **Budget Tracking:** Set monthly budgets for each category and get alerts when you’re nearing your limits.
- **Data Export:** Download your expense data as CSV for further analysis or backup.
- **User Authentication:** Secure login to protect your financial data.

## Telegram Bot Integration

Spendie offers a convenient Telegram bot to manage your expenses directly from Telegram!  
**Try it here:** [@TrackWithSpendie_bot](https://t.me/TrackWithSpendie_bot)

### Bot Features

- Add expenses via chat commands
- Get instant summaries and reports
- Access your spending data from anywhere on Telegram

### How to Use

1. Open Telegram and search for [@TrackWithSpendie_bot](https://t.me/TrackWithSpendie_bot)
2. Start the bot and follow the instructions to link your account (if required)
3. Use the provided commands to add expenses, view reports, and manage your budget

The bot is actively deployed on [Render](https://render.com/), ensuring high availability.

## Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/namanshetty25/Spendie.git
   cd Spendie
   ```

2. **Create a Virtual Environment** (Optional but recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

You can start Spendie by running:

```bash
python main.py
```

Or, if there is a specific script (replace as needed):

```bash
python spendie.py
```

Follow the prompts to add, view, and manage expenses.

## Project Structure

```
Spendie/
├── data/                # Stores database or CSV files
├── src/                 # Source code for the application
│   ├── models.py        # Data models
│   ├── views.py         # User interface logic (CLI/GUI)
│   ├── utils.py         # Helper functions
│   └── ...              
├── tests/               # Unit and integration tests
├── requirements.txt     # Python dependencies
├── README.md            # Project documentation
└── main.py              # Application entry point
```

## Contributing

## License

This project is licensed under the [MIT License](LICENSE).

## Author

- [namanshetty25](https://github.com/namanshetty25)

