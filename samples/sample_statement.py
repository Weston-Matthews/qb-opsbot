# A fictional settlement statement laid out the way config.example.json expects.
# Used by the tests, and by make_sample_statement.py to write an .xlsx you can open or feed to the bot.
# Every name and number here is made up.

ROWS, COLS = 40, 8


def build_grid():
    g = [["" for _ in range(COLS)] for _ in range(ROWS)]

    def put(r, c, v):
        g[r][c] = v

    put(0, 0, "Settlement Statement (SAMPLE DATA)")
    put(1, 0, "Contract Number"); put(1, 7, "C-1001")
    put(2, 0, "Payment Date"); put(2, 7, 43861.0)          # Excel serial for 01/31/2020
    put(3, 0, "Customer:")
    put(5, 0, " Acme Salvage Co")                          # statements print a leading space

    # Lot 1: metals paid on assay (Palladium is split over two breakdown rows)
    put(7, 0, "Lab Control"); put(7, 1, "LC-20-0001")
    put(8, 0, "Metals Paid on Assay")
    put(9, 0, "Metal"); put(9, 4, "Troy oz"); put(9, 6, "Amount")
    put(10, 0, "Platinum"); put(10, 4, 1.23456); put(10, 6, 1100.00)
    put(11, 0, "Palladium")
    put(12, 4, 0.5); put(12, 6, 1000.00)
    put(13, 4, 0.25); put(13, 6, 500.00)
    put(14, 0, "Rhodium"); put(14, 4, 0.1); put(14, 6, 800.00)
    put(16, 5, "TOTAL "); put(16, 6, 3400.00)

    # Lot 2: material not on assay, paid per piece (pieces x rate)
    put(18, 0, "Lab Control"); put(18, 1, "LC-20-0002")
    put(19, 0, "Material Not on Assay")
    put(20, 4, "Item"); put(20, 5, "Pcs"); put(20, 6, "Rate")
    put(21, 4, "Widget Core - Large"); put(21, 5, 10.0); put(21, 6, 25.00)
    put(22, 4, "Sample Weight - Lot 7"); put(22, 5, 1.0); put(22, 6, 40.00)
    put(23, 4, "Oxygen Sensor"); put(23, 5, 20.0); put(23, 6, 3.00)
    put(24, 4, "Copper Scrap"); put(24, 5, 100.0); put(24, 6, 3.00)

    # Fees, including one advance payment with its interest and wire fee
    put(27, 0, "Fees")
    put(28, 4, "Treatment Charge"); put(28, 5, -150.00)
    put(29, 4, "Less Advance Payment"); put(29, 5, -2000.00)
    put(30, 4, "Interest on Advance Payment"); put(30, 5, -12.50)
    put(31, 4, "Wire Transfer Fee (Advance)"); put(31, 5, -25.00)
    put(32, 4, "Interest on Final Payment"); put(32, 5, -3.10)
    put(33, 4, "Wire Transfer Fee (Final)"); put(33, 5, -25.00)
    put(34, 4, "TOTAL"); put(34, 5, -2215.60)

    put(36, 0, "FINAL BALANCE DUE"); put(36, 1, "NORTH"); put(36, 7, 1834.40)
    return g


class GridSheet:
    # Minimal stand-in for xlrd's Sheet: nrows, ncols, cell_value(row, col)
    def __init__(self, grid):
        self.grid = grid
        self.nrows = len(grid)
        self.ncols = len(grid[0]) if grid else 0

    def cell_value(self, r, c):
        return self.grid[r][c]
