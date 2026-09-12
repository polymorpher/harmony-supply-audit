# Curated input provenance

## Final 2024 mint-response blacklist

`blacklisted-addresses-2024-final.txt` is byte-for-byte identical to:

`harmony-one/ansible@32690a2cdbf792a3c0623492c54211869b2d7acf`

Path:

`playbooks/roles/node/templates/blacklist.txt`

SHA-256:

`a624331ec55f23090a10951c4e5e2d8d0ec10b9985099e299ad7e952d0e03af7`

It contains 71 lines and 70 unique valid addresses. The duplicate is
`one17ne52ywldl9nvfqlgjy8e2y02drauctsk54k5k`.

This is not the complete 2021–2022 wallet-theft blacklist.

## Report-identified wallet-theft addresses

`reported-wallet-theft-perpetrators.txt` contains 17 Harmony addresses that
the supplied reports explicitly labeled perpetrator- or hacker-controlled.
The filename preserves the original extraction name; this repository is
recording the reports' labels, not making an independent identity or legal
finding.

`reported-wallet-theft-perpetrators.csv` records the role and report
reference as `report_assigned_role`. It deliberately excludes victims, a suspect-only validator,
contracts and exchanges, Ethereum-only contextual addresses, and merely
suspicious post-Tornado addresses.

Source report hashes:

| Report | SHA-256 |
|---|---|
| `Report #1: Harmony Chrome Extension Wallet Theft Incidents` | `c4f56ee0de9359163483c52bb090e630789fa258ab55dd90e1009d6ef8b4cafe` |
| `Report #2: Harmony Chrome Extension Wallet Thefts` | `c6108a62f59093c4f35a9702edc2d3fd499fe84a37ffad2b0964aab62c7834c1` |
| `Report #3: Harmony Extension Wallet Thefts` | `1f143de9dd1ecdf7d68e003cf0a2f604bab395e449dc71cd11a911bdf11c94b2` |
| `Report #4: Analysis of a ~$50M theft on Harmony` | `107c42597bc23e8ec19d8308a487eafcb7168463087d20fd455d421e47e5e9c6` |

The reports themselves are not republished in this repository.
