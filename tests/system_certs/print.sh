# Don't try to convert our subject string to a windows path
export MSYS_NO_PATHCONV=1

# Create CA (root key and cert)
openssl genrsa -out local-ca.key 4096
openssl req -x509 -new -nodes -key local-ca.key -sha256 -days 1825 -out local-ca.pem -subj '/C=/ST=/L=/O=/CN=local-ca'

# Key and csr for the server
openssl genrsa -out testserver.key 4096
openssl req -new -key testserver.key -out testserver.csr -subj '/C=/ST=/L=/O=/CN=localhost'

# Cert for the server signed by the CA
openssl x509 -req -in testserver.csr -CA local-ca.pem -CAkey local-ca.key \
-CAcreateserial -out testserver.crt -days 825 -sha256 -extfile testserver.ext
