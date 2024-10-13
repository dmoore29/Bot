import json
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
import time


################################################################
#                       CONFIGURATION                          #
################################################################

# PICKUP_METHOD = "IN_STORE" # In store typically means same day so is likely unavailible
PICKUP_METHOD = "SHIP"
# SHIP_METHOD = "MY_ADDRESS"
SHIP_METHOD = "MY_STORE"
STORE_ZIP_CODE = 17363

################################################################
################################################################

# Configure logging
logging.basicConfig(
    filename='./logs/app.log',  # Path where logs will be stored for CloudWatch
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger()
service = Service(executable_path="chromedriver.exe")

chrome_options = Options()
chrome_options.add_argument("--headless")  # Run headless
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

session = boto3.session.Session()
dynamodb = boto3.client('dynamodb', region_name='us-east-1')

# driver = webdriver.Chrome(service=service)

wait = WebDriverWait(driver, 5)

def start_bot():
    is_product_availible = False
    first_run = True

    config = fetch_configuration("PurchaseBot", "finewineandgoodspirits")
    retry_interval = config['retry_interval']
    product = config['products']

    while not is_product_availible:
        get_product(product[0])

        if first_run:
            confirm_age()
            login()
            first_run = False

        is_product_availible = check_if_availible()

        if is_product_availible:
            add_to_cart()

            try:
                checkout()
            except Exception as e:
                logger.error("Failed checkout. Trying again")
                logger.error(f"Exception: {e}")
                try:
                    time.sleep(2)
                    get_product(product_urls[0])
                    checkout()
                except:
                    logger.error("Failed checkout. Quitting")
                    logger.error(f"Exception: {e}")
                    close()
        time.sleep(retry_interval)

    driver.quit()
    # TODO: Handle logic to retry checkout


def get_product(product):

    # TEMP CODE. UPDATE THIS
    product_url = product['url']
    name = product['name']

    if product_url is not None:
        driver.get(product_url)
    elif product_url is not None:
        load_home_page()
        confirm_age()
        search_for_product(name)
    else:
        logger.error("Product name or URL must be specified")
        driver.quit()


def login():
    time.sleep(1)
    try:
        # Wait for the button to be clickable
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@class='modal-header-login link' and .//span[text()='Log In']]")))
        login_button.click()  # Click the button
        logger.info("Clicked login button")
    except:
        logger.error("Log In button did not become clickable in time.")

    time.sleep(1)

    secret = get_secret()

    print(secret)

    email_input = wait.until(EC.visibility_of_element_located((By.ID, "authentication_header_login_form_email")))
    email_input.clear()  # Clear any existing text
    email_input.send_keys(secret['email'])

    password_input = wait.until(EC.visibility_of_element_located((By.ID, "authentication_header_login_form_password")))
    password_input.clear()  # Clear any existing text
    password_input.send_keys(secret['password'])

    time.sleep(1)

    try:
        final_login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and @aria-label='LOGIN']")))
        final_login_button.click()  # Click the button
        logger.info("Logged in successfully")
    except:
        logger.error("Error while logging in...")
        close()

def load_home_page():
    driver.get("https://finewineandgoodspirits.com")
    logger.info("Loaded home page")

def confirm_age():
    try:
        button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Yes, Enter into the site']")))
        button.click()
        logger.info("Age confirmed")
    except:
        pass


def search_for_product(name):
    input_field = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@aria-label='search']")))
    input_field.send_keys(name)
    input_field.send_keys(Keys.RETURN)
    logger.info(f"Searched for product: {name}")

    time.sleep(2)
    input_field = wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, name)))
    link = driver.find_element(By.PARTIAL_LINK_TEXT, name)
    link.click()
    time.sleep(2)


def check_if_availible():
    try:
        # Wait for the button to be present in the DOM
        wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='add-to-cart-button button full-width false' and text()='Coming Soon']")))
        logger.info("Product not yet availible")
        return False
    except:
        logger.info("Product appears to be in stock...")
        return True  # Button does not exist


def add_to_cart():
    time.sleep(1)

    try:
        availability_button = wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='link' and text()='Click to see availability.']")))
        availability_button.click()
    except:
        logger.error("Error while checking availability...")

    time.sleep(1)

    if PICKUP_METHOD == "IN_STORE":
        logger.info("Picking up in store.")
        try:
            ship_button = wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='button fulfillment ' and .//p[text()='Pick Up']]")))
            driver.execute_script("arguments[0].click();", ship_button)
        except:
            logger.error("Error while clicking pick up...")

        time.sleep(1)

        try:
            search_input = wait.until(EC.visibility_of_element_located((By.NAME, "fulltext")))
            search_input.clear()  # Clear any existing text
            search_input.send_keys(STORE_ZIP_CODE)  # Enter the search value
        except:
            logger.error("Error while searching for store...")

    elif PICKUP_METHOD == "SHIP":
        logger.info("Shipping.")
        try:
            ship_button = wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='button fulfillment ' and .//p[text()='Ship']]")))
            driver.execute_script("arguments[0].click();", ship_button)
        except:
            logger.error("Error while clicking ship...")
    else:
        logger.error("Unsupported shipping method. Must be either IN_STORE or SHIP")

    time.sleep(1)

    try:
        add_to_cart_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@class='add-to-cart-button button full-width false']")))
        add_to_cart_button.click()
    except:
        logger.error("Error while adding to cart...")
        close()


def checkout():
    logger.info("Checking out")

    time.sleep(1)
        
    try:
        cart_button = wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='miniCart__openButton icon--before icon-cart tooltip-icon' and @aria-label='Cart']")))
        cart_button.click()
    except:
        logger.error("Error while clicking cart...")
        raise

    time.sleep(1)
        
    try:
        checkout_button = wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='button cart-link' and text()='CHECKOUT']")))
        checkout_button.click()
        logger.info("Proceeded to checkout")
    except:
        logger.error("Error while going to checkout...")
        raise

    time.sleep(1)

    click_popup_close_button()

    # Phone number and use contact button seems like a one time setup

    # try:
    #     phone_input = wait.until(EC.visibility_of_element_located((By.ID, "contact_info_profile-phoneNumber")))
    #     phone_input.clear()  # Clear any existing text
    #     phone_input.send_keys(7178141862)  # Enter the phone number
    # except:
    #     logger.error("Failed entering phone number...")
          
    # try:
    #     contact_info_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and text()='USE CONTACT INFO']")))
    #     contact_info_button.click()
    # except TimeoutException:
        # logger.error("Failed to click use contact button...")

    if SHIP_METHOD == "MY_STORE":
        try:
            # Wait for the radio button to be present and clickable
            my_store_button = wait.until(EC.element_to_be_clickable((By.ID, "shipToMyStore")))
            my_store_button.click()  # Click the radio button to select it
            logger.info("Ship to My Store radio button selected.")
        except:
            logger.error("Ship to My Store radio button did not become clickable in time.")
            raise

        time.sleep(1)

        click_popup_close_button()

        try:
            # Wait for the button to be clickable
            continue_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Continue to Payment']")))
            continue_button.click()  # Click the button
            logger.info("Continue to Payment button clicked.")
        except:
            logger.error("Continue to Payment button did not become clickable in time.")
            raise


    time.sleep(3)

    click_popup_close_button()
    
    try:
        security_code_input = wait.until(EC.visibility_of_element_located((By.ID, "csv-code")))
        security_code_input.clear()  # Clear any existing text
        security_code_input.send_keys(7173)  # Enter the security code
        logger.info("Entered security code")
    except:
        logger.error("Failed entering security code...")
        raise

    time.sleep(2)

    click_popup_close_button()

    try:
        place_order_button = wait.until(EC.element_to_be_clickable((By.ID, "place-order-button")))
        # place_order_button.click()
        logger.info("Placed order")
    except:
        logger.error("Failed to place order")
        raise

    time.sleep(10)

def click_popup_close_button():
    try:
        # Wait for the close button to be clickable
        close_button = driver.find_element(By.CLASS_NAME, "ltkpopup-close")
        close_button.click()  # Click the close button
        logger.info("Popup close button clicked.")
    except:
        pass

def was_checkout_successful():
    return True


def close():
    driver.quit()


def get_secret():

    secret_name = "finewineandgoodspirits"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except Exception as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    return json.loads(get_secret_value_response['SecretString'])

def fetch_configuration(table_name, bot_name):
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={'botName': {'S': bot_name}}
        )
        if 'Item' in response:
            return parse_config(response['Item'])
        else:
            raise ValueError("Configuration not found for bot.")
    except (NoCredentialsError, PartialCredentialsError) as e:
        print("Error fetching configuration:", e)

def parse_config(item):
    return {
        "bot_name": item['botName']['S'],
        "products": [
            {
                "url": product['M'].get('url', {}).get('S', None),
                "name": product['M'].get('name', {}).get('S', None),
                "quantity": int(product['M']['quantity']['N']),
                "status": product['M']['status']['S']
            }
            for product in item['products']['L']
        ],
        "retry_interval": int(item['retryInterval']['N'])
    }

start_bot()