# Marketplace order handling

## Requirements

1. A customer can place an order for one or more products from a single merchant.
2. Every order has a delivery address and a chosen delivery slot.
3. The order also records the payment method the customer used and the total charged.
4. An order is placed, then confirmed by the merchant, then shipped; a customer may cancel it until it is shipped.
5. A merchant must confirm or decline an order within 2 hours, otherwise the order expires.
6. Once an order is shipped it must never be modified, and it must not be cancelled.
7. An order that has been declined cannot be confirmed later.
8. A customer cannot place an order for a product that is not in stock.
9. Refunds are never issued for an order that was not shipped.
10. The merchant sees the number of open orders per product on the dashboard.

## Constraints

- Team of 3, Python, PostgreSQL available.
