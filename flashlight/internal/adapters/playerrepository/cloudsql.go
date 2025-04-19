package playerrepository

import "fmt"

// https://cloud.google.com/sql/docs/mysql/connect-functions
func GetCloudSQLConnectionString(dbUsername, dbPassword, unixSocketPath string) string {
	return fmt.Sprintf(
		"user=%s password=%s database=%s host=%s",
		dbUsername,
		dbPassword,
		DB_NAME,
		unixSocketPath,
	)
}
