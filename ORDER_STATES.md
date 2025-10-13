# Public.com API Order States Documentation

This document provides comprehensive documentation of all order states used by the Public.com brokerage API, based on industry standards and actual implementation experience.

## Order State Categories

### Active States (Order Still Working)
Orders in these states are still active in the market and may receive fills or state changes:

- **NEW**: Order submitted and accepted, awaiting market execution
- **PARTIALLY_FILLED**: Part of order executed, remainder still active
- **PENDING_REPLACE**: Order modification requested but not yet confirmed
- **PENDING_CANCEL**: Cancellation requested but not yet confirmed

### Terminal States (Order Complete)
Orders in these states are finished and will not receive further fills:

- **FILLED**: Entire order quantity successfully executed
- **CANCELLED**: Order successfully cancelled (may have partial fills)
- **QUEUED_CANCELLED**: Order cancelled while in queue (pre-market, after-hours)
- **REJECTED**: Order rejected by broker/exchange (invalid parameters, insufficient funds)
- **EXPIRED**: Order expired due to time-in-force limit (day order, GTD)
- **REPLACED**: Order successfully modified/replaced by new version

## Complete Order State Reference

| Order State        | Category | Description |
|--------------------|----------|-------------|
| NEW               | Active   | Order submitted and accepted by broker, awaiting market execution |
| PARTIALLY_FILLED  | Active   | Part of order quantity executed, remainder still working in market |
| CANCELLED         | Terminal | Order successfully cancelled (may include partial fills before cancellation) |
| QUEUED_CANCELLED  | Terminal | Order cancelled while queued (e.g., pre-market, after-hours processing) |
| FILLED            | Terminal | Entire order quantity successfully executed |
| REJECTED          | Terminal | Order rejected by broker/exchange (insufficient funds, invalid parameters) |
| PENDING_REPLACE   | Active   | Order modification requested but not yet confirmed or applied |
| PENDING_CANCEL    | Active   | Cancellation requested but not yet processed (may still fill) |
| EXPIRED           | Terminal | Order expired due to time-in-force expiration (GTD, day orders) |
| REPLACED          | Terminal | Order successfully modified/replaced by new version |

## Important Implementation Notes

### PARTIALLY_FILLED is Active, Not Terminal
A critical distinction: **PARTIALLY_FILLED means the order is still working**, not that it failed or is done. This is the most common source of bugs in order handling logic.

```python
# CORRECT - PARTIALLY_FILLED is active
if order_status.status in ['NEW', 'PARTIALLY_FILLED', 'PENDING_REPLACE', 'PENDING_CANCEL']:
    # Order is still active, continue waiting or processing
    
# INCORRECT - treating PARTIALLY_FILLED as terminal  
if order_status.status == 'PARTIALLY_FILLED':
    return False  # WRONG! Order is still working
```

### Cancellation Success Detection
When verifying order cancellations, multiple states indicate successful cancellation:

```python
# All these states mean cancellation succeeded
successful_cancellation = order_status.status in [
    'CANCELLED', 'QUEUED_CANCELLED', 'REJECTED', 'EXPIRED'
]
```

### Fill Tracking
Even cancelled orders may have partial fills that must be accounted for:

```python
# Always check filled quantity, even for cancelled orders
filled_qty = int(float(order_status.filledQuantity)) if hasattr(order_status, 'filledQuantity') and order_status.filledQuantity else 0

if order_status.status in ['CANCELLED', 'QUEUED_CANCELLED']:
    # Order was cancelled, but may have partial fills
    return True, filled_qty  # (cancelled_successfully, quantity_filled)
```

## Order Lifecycle Examples

### Successful Full Fill
```
NEW → PARTIALLY_FILLED → FILLED
```

### Cancelled with Partial Fill
```
NEW → PARTIALLY_FILLED → PENDING_CANCEL → CANCELLED
```
*Note: Order was cancelled but partial fills occurred before cancellation*

### Order Modification
```
NEW → PENDING_REPLACE → REPLACED
```
*Original order is now REPLACED, new order starts as NEW*

### Rejection
```
NEW → REJECTED
```
*Order rejected immediately due to invalid parameters*

### Expiration
```
NEW → PARTIALLY_FILLED → EXPIRED
```
*Day order expires at market close with partial fills*

## Code Implementation Patterns

### Wait for Fill Logic
```python
def wait_for_fill(order_id):
    while True:
        status = get_order_status(order_id)
        
        if status.status == 'FILLED':
            return True  # Complete success
            
        elif status.status in ['PARTIALLY_FILLED', 'NEW']:
            continue  # Still working, keep waiting
            
        elif status.status in ['PENDING_CANCEL', 'PENDING_REPLACE']:
            continue  # Transitional state, keep waiting
            
        elif status.status in ['CANCELLED', 'QUEUED_CANCELLED', 'REJECTED', 'EXPIRED', 'REPLACED']:
            return False  # Terminal - no more fills possible
```

### Cancellation Verification
```python
def verify_cancellation(order_id):
    status = get_order_status(order_id)
    filled_qty = get_filled_quantity(status)
    
    if status.status in ['CANCELLED', 'QUEUED_CANCELLED', 'REJECTED', 'EXPIRED']:
        return True, filled_qty  # Successfully cancelled
        
    elif status.status == 'FILLED':
        return False, filled_qty  # Couldn't cancel - already filled
        
    elif status.status in ['NEW', 'PARTIALLY_FILLED', 'PENDING_CANCEL', 'PENDING_REPLACE']:
        raise Exception(f"Order still active after cancellation attempt: {status.status}")
        
    elif status.status == 'REPLACED':
        raise Exception(f"Order was replaced instead of cancelled")
```

## Error Handling

### System Inconsistency Detection
If an order shows active states after verified cancellation, this indicates a system problem:

```python
if status.status in ['NEW', 'PARTIALLY_FILLED', 'PENDING_CANCEL'] and cancellation_was_verified:
    raise Exception(f"System inconsistency: verified cancellation but order still active with status {status.status}")
```

### Unknown State Handling
Always handle unknown states defensively:

```python
else:
    logger.error(f"Unknown order status: {status.status}")
    raise Exception(f"Unknown order status: {status.status}")
```

## Testing Scenarios

When testing order handling logic, ensure coverage of:

1. **Happy Path**: NEW → FILLED
2. **Partial Fills**: NEW → PARTIALLY_FILLED → FILLED
3. **Cancellation**: NEW → PENDING_CANCEL → CANCELLED
4. **Partial + Cancel**: NEW → PARTIALLY_FILLED → PENDING_CANCEL → CANCELLED
5. **Rejection**: NEW → REJECTED
6. **Expiration**: NEW → EXPIRED
7. **Replacement**: NEW → PENDING_REPLACE → REPLACED
8. **Race Conditions**: Order fills while cancellation is pending

## References

- Based on FIX Protocol standards for order lifecycle management
- Aligned with common brokerage API implementations (Alpaca, TradeStation, Questrade)
- Validated through Public.com API testing and implementation experience
- Grok AI analysis confirms alignment with industry standards

---

*Last Updated: October 11, 2025*  
*Version: 1.0*  
*Maintainer: Walk Limit Engine Team*