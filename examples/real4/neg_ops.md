# Order service

## Requirements
- Users can cancel an order that has not yet shipped.
- The exporter must not block the request; it writes the CSV asynchronously and emails a link.
- Notify the warehouse manager when a shipment has not been scanned within 4 hours of dispatch.
- Users can archive projects they no longer need; archived projects are not deleted and can be restored.
- The scheduler retries a failed export up to 3 times; it does not retry a validation error.
- Admins can unpublish a listing; an unpublished listing is not visible to buyers but remains editable.

## Constraints
- Python, PostgreSQL. Team: 3 engineers.
