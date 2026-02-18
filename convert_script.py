import os
import glob
import pandas as pd
import sys

# Set encoding for stdout
sys.stdout.reconfigure(encoding="utf-8")


def convert_xlsx_to_csv():
    # Define the folder containing the xlsx file
    # Use absolute path to ensure correctness
    base_dir = os.path.dirname(os.path.abspath(__file__))
    folder_path = os.path.join(base_dir, "表格")

    print(f"Searching in: {folder_path}")

    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    # Search for .xlsx files in the folder
    xlsx_files = glob.glob(os.path.join(folder_path, "*.xlsx"))

    print(f"Found files: {xlsx_files}")

    if len(xlsx_files) == 0:
        print(f"Error: No .xlsx file found in '{folder_path}' folder.")
        return
    elif len(xlsx_files) > 1:
        print(
            f"Error: Multiple .xlsx files found in '{folder_path}' folder. Expecting only one."
        )
        return

    source_file = xlsx_files[0]
    output_file = os.path.join(base_dir, "board.csv")

    print(f"Converting file: {source_file}")

    try:
        # Read the Excel file
        df = pd.read_excel(source_file, engine="openpyxl")

        # Keep only the first 500 rows
        df_head = df.head(500)

        # Save to CSV
        df_head.to_csv(output_file, index=False, encoding="utf-8-sig")
        print(
            f"Successfully converted '{source_file}' to '{output_file}' with {len(df_head)} rows."
        )

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    convert_xlsx_to_csv()
