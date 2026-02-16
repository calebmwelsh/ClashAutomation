# Clash Automation Workflow

> [!WARNING]
> **Project Status: Early Alpha / Experimental.**
> This automation is active development and is considered **buggy and not foolproof**. Use with caution and expect occasional failures.

An advanced automation system for Clash of Clans, designed to handle multi-account management, resource collection, and automated base progression.

## 📁 Project Structure

- `main.py`: The primary entry point for the automation.
- `utils/`: Core functional modules.
- `utils/baseconfig/static_config.toml`: Central configuration for shared UI elements and event-specific data.
- `data/`: Stores session screenshots, logs, and templates.
- `setup_utils/`: Utilities for initial base recording (`setup_base.py`).
- `input_tools/`: Helper scripts for manual adjustments (e.g., `get_special_troop_color.py`).

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **[Google Play Games Beta](https://play.google.com/googleplaygames)** installed on Windows.
- **[Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)**: Required for vision-based text extraction.
    - Install and ensure `tesseract` is in your system PATH.

### Display & Resolution

The system uses a percentage-based coordinate system with a reference target of **1728 x 1080**.
- **Support**: While optimized for the reference resolution, the code supports scaling and should work on any resolution.
- **Scaling**: Windows Display Scaling **MUST** be set to 100% for coordinate accuracy.
- **Game Window**: The automation will attempt to find and focus the "Clash of Clans" window automatically.

### Installation

1.  **Clone the repository**.
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Initial Configuration**:
    - Create a `config.toml` file by copying the template:
      ```bash
      copy config.template.toml config.toml
      ```
    - Open `config.toml` and update the filesystem paths to match your installation.

### ⚙️ Account Configuration

1.  **Start the Setup Utility**:
    ```bash
    python setup_utils/setup_base.py
    ```
    Follow the prompts to record base-specific coordinates. This creates `baseconfig_*.toml` files in `utils/baseconfig/`.

### 🐉 Special Troops & Events

During special events, the `static_config.toml` may require manual updates if the GitHub repository hasn't been updated yet:

1.  **Fixing Troop Colors**:
    - Run the helper script to sample the current event troop's color and update `static_config.toml` automatically:
      ```bash
      python input_tools/get_special_troop_color.py
      ```
2.  **Manual Counts**:
    - You MUST manually update `special_troop_counts` in `static_config.toml`. Enter the amount of special troops per tile (e.g., `[10]` if you have 10 per troop icon).

### ⚡ Usage

Run the main automation script:
```bash
python main.py
```

## 🛠️ Key Features

- **Multi-Account Switching**: Automatically rotates through accounts defined in `utils/baseconfig/`.
- **Intelligent Resource Collection**: Detects and collects resources in both Home and Builder bases.
- **Attack Loop**: Automated troop deployment to fill storage when upgrades are needed.
- **Vision-Powered**: Uses Tesseract OCR and RGB analysis for UI interaction.

## 🤝 Contributing

Contributions are welcome! If you find a bug or have a suggestion for improvement, feel free to open an issue or submit a pull request.

---

ClashAutomation

An experimental automation framework for Clash of Clans that manages multiple accounts and base progression using vision-based detection. Designed for Windows via Google Play Games Beta, the system uses a flexible coordinate system and OCR for robust UI interaction. 