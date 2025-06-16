# mauzenfan/server/api/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Child # Assuming Child is in the same app's models
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Child)
def create_child_proxy_user(sender, instance, created, **kwargs):
    """
    Automatically creates a proxy User account when a new Child is created,
    if one doesn't already exist.
    """
    if created and not instance.proxy_user:
        proxy_username = f"child_{instance.id}_proxy"
        proxy_user_email = f"{proxy_username}@mauzenfan.app" # Dummy email

        # Check if user already exists (should be rare if child.id is unique in username)
        existing_user = User.objects.filter(username=proxy_username).first()
        if existing_user:
            logger.warning(f"Proxy user {proxy_username} already exists. Attempting to link if unlinked.")
            # Check if this existing user is already a proxy for another child
            if not hasattr(existing_user, 'messaging_child_profile') or existing_user.messaging_child_profile is None:
                instance.proxy_user = existing_user
                # Use direct update to avoid recursion
                Child.objects.filter(pk=instance.pk).update(proxy_user=existing_user)
                logger.info(f"Linked existing user '{proxy_username}' to child {instance.name} (ID: {instance.id})")
            else:
                # This is an unexpected state: username conflict or already linked.
                logger.error(f"Cannot link existing user '{proxy_username}' to child {instance.name} (ID: {instance.id}). User might be linked to another child or is not a proxy.")
            return # Stop further processing

        # Create the proxy user if it doesn't exist
        try:
            user = User.objects.create_user(
                username=proxy_username,
                email=proxy_user_email,
                # No password needed as set_unusable_password will be called
            )
            user.set_unusable_password()
            user.is_active = False # Proxy users are not active for login
            user.save()

            # Update the Child instance with the new proxy_user
            # Using a direct update to avoid re-triggering the post_save signal recursively
            Child.objects.filter(pk=instance.pk).update(proxy_user=user)
            logger.info(f"Created proxy user '{proxy_username}' for child {instance.name} (ID: {instance.id})")
        except Exception as e:
            logger.error(f"Error creating proxy user for child {instance.id}: {e}", exc_info=True)
