STATUS_COLORS = {
    "Open":             "#ffffff",
    "In Progress":      "#aaaaaa",
    "Waiting on Parts": "#888888",
    "Ready for Pickup": "#ffffff",
    "Completed":        "#555555",
    "Cancelled":        "#333333",
}
STATUSES = list(STATUS_COLORS.keys())

REPAIR_DAYS = {
    "Virus/Malware Removal":                2,
    "OS Reinstall / Recovery":              3,
    "Hardware Replacement (RAM/SSD/HDD)":   5,
    "Screen Replacement":                   7,
    "Keyboard / Input Repair":              7,
    "Power Jack / Charging Port":           10,
    "Data Recovery":                        5,
    "Network / WiFi Troubleshooting":       1,
    "Software Installation & Setup":        1,
    "Liquid Damage Assessment":             3,
    "Diagnostic Only":                      1,
    "Custom / Other":                       None,
}
REPAIR_PRICE = {
    "Virus/Malware Removal":                80,
    "OS Reinstall / Recovery":              120,
    "Hardware Replacement (RAM/SSD/HDD)":   95,
    "Screen Replacement":                   180,
    "Keyboard / Input Repair":              110,
    "Power Jack / Charging Port":           130,
    "Data Recovery":                        150,
    "Network / WiFi Troubleshooting":       60,
    "Software Installation & Setup":        50,
    "Liquid Damage Assessment":             75,
    "Diagnostic Only":                      40,
    "Custom / Other":                       None,
}
REPAIR_TYPES = list(REPAIR_DAYS.keys())

DEVICE_TYPES = [
    "Desktop PC", "Laptop", "MacBook", "iMac",
    "Tablet", "Printer", "NAS / Server", "Other"
]
PRIORITIES = ["Standard", "Rush", "Critical"]

PART_CATEGORIES = [
    "RAM", "SSD / HDD", "Screen / Display", "Battery", "Keyboard",
    "Power Adapter", "Motherboard", "CPU", "GPU", "Cooling / Fan",
    "Cable / Connector", "Enclosure / Case", "Peripheral", "Software", "Other"
]

DEVICE_CONDITIONS = ["Excellent", "Good", "Fair", "Poor", "For Parts"]
DEVICE_STATUSES   = ["Staging", "Ready for Sale", "Sold"]
