from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    shopkeeper_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "role", "phone_number", "is_active", "date_joined",
            "shopkeeper", "shopkeeper_name",
        ]
        read_only_fields = ["id", "date_joined"]

    def get_shopkeeper_name(self, obj):
        return obj.shopkeeper.name if obj.shopkeeper_id else None


class CreateUserSerializer(serializers.ModelSerializer):
    """SRS 4.1: 'Admin can create additional read-only users.' Extended so
    the admin can also create a SHOPKEEPER-role login for an existing
    Shopkeeper record, so that shopkeeper can sign into the app and see
    their own laptops / payments / remaining balance only."""
    password = serializers.CharField(write_only=True, validators=[validate_password])

    shopkeeper_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "role", "phone_number", "password", "shopkeeper",
            # These three were missing from the response, even though the
            # user WAS created successfully -- the iOS AppUser.Codable model
            # requires "is_active" (non-optional Bool) and decoding failed
            # with every field missing, surfacing as a false
            # "Something went wrong reading the server response" error on
            # an already-successful create. Retrying then hit the real
            # uniqueness errors on username/shopkeeper from the row that
            # had actually been created the first time.
            "is_active", "date_joined", "shopkeeper_name",
        ]
        read_only_fields = ["id", "is_active", "date_joined"]

    def get_shopkeeper_name(self, obj):
        return obj.shopkeeper.name if obj.shopkeeper_id else None

    def validate(self, attrs):
        role = attrs.get("role", User.READ_ONLY)
        shopkeeper = attrs.get("shopkeeper")
        if role == User.SHOPKEEPER and not shopkeeper:
            raise serializers.ValidationError(
                {"shopkeeper": "Pick which shopkeeper this login belongs to."}
            )
        if role != User.SHOPKEEPER and shopkeeper:
            raise serializers.ValidationError(
                {"shopkeeper": "Only a SHOPKEEPER-role account can be linked to a shopkeeper."}
            )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)  # SRS 13: never store passwords as plain text
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)