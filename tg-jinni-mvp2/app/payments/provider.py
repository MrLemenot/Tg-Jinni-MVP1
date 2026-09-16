from dataclasses import dataclass

@dataclass
class PaymentIntent:
    payment_id: str
    checkout_url: str

class PaymentProvider:
    async def create(self, payment_id: str, amount_rub: int, description: str) -> PaymentIntent:
        # Adapter point for YooKassa/Telegram Payments/another provider.
        return PaymentIntent(payment_id=payment_id, checkout_url=f'/pay/{payment_id}')
