tail -f $(find /var/lib/mysql -name *-slow.log) | awk '{ if ($0 ~ "# Time: ") { printf "\n%s", $0; fflush() } else { printf " %s", $0; fflush() } }'
