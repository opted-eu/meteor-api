echo "Importing Data from Work Packages"
echo "WP3..."
./tools/wp3migrate.sh
echo "WP4..."
python3 tools/wp4_import.py
echo "WP5..."
python3 tools/wp5_import.py
echo "WP2..."
python3 tools/wp2_import.py