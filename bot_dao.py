import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

def fetch_configuration(table_name, bot_name):
    dynamodb = boto3.resource('dynamodb')

    try:
        # Get the table resource
        table = dynamodb.Table(table_name)
        
        # Fetch the item using the resource interface
        response = table.get_item(Key={'botName': bot_name})
        
        if 'Item' in response:
            return parse_config(response['Item'])
        else:
            raise ValueError("Configuration not found for bot.")
    
    except (NoCredentialsError, PartialCredentialsError) as e:
        raise RuntimeError("Error fetching configuration:", e)


def insert_configuration(table_name, bot_config):
    dynamodb = boto3.resource('dynamodb')

    try:
        # Get the table resource
        table = dynamodb.Table(table_name)
        
        # Insert the item into the table using put_item
        response = table.put_item(Item=bot_config)
        
        # Return a confirmation message or response data
        return response

    except (NoCredentialsError, PartialCredentialsError) as e:
        raise RuntimeError("Error inserting configuration:", e)


def parse_config(item):
    return {
        "botName": item['botName'],
        "products": [
            {
                "url": product.get('url'),  # Resource handles types
                "name": product.get('name'),
                "quantity": int(product['quantity']),
                "status": product['status']
            }
            for product in item['products']
        ],
        "retryInterval": int(item['retryInterval'])
    }