echo "Changing WP3 backup files..."
python3 -u tools/alter_backup.py
echo "Sucess!"
echo "Deleting all Data from DGraph..."
curl -X POST localhost:8080/alter -d '{"drop_op": "DATA"}'
echo "Success!"
echo "Loading altered WP3 backup"
dgraph live --files data/g01.rdf --schema data/g01.schema --zero localhost:5080
echo "Success!"
echo "Running migration scripts..."
python3 -u tools/wp3migrate.py