import json
import logging
import random
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
from bot_dao import fetch_configuration, insert_configuration
import time
from datetime import datetime


###
# TODO: Empty cart
# TODO: Validate price
# TODO: Fix searching
# TODO: Speed up


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
chrome_options.add_argument("--incognito")

session = boto3.session.Session()

def start_bot():
    is_product_availible = False
    product_count = 1
    index = 0  # Initialize the index

    while product_count > 0:
        first_run = True
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_window_size(1920, 1080)

        wait = WebDriverWait(driver, 8)
        time.sleep(4)

        config = fetch_configuration("PurchaseBot", "finewineandgoodspirits")
        secret = get_secret()
        logger.info(f"Retrieved config: {config}")
        retry_interval = config['retryInterval']
        product_count = len(config['products'])


        # logger.info(f"TEMP: Product count, {product_count}, is greater than 0")
        while index < product_count:
            # logger.info(f"TEMP: Index, {index}, is less than product count, {product_count}")
            product = config['products'][index]
            if product['status'] != "coming_soon":
                logger.info("Already purchased")
                index += 1
                continue
            try:
                get_product(product, driver, wait)
            except:
                logger.error("Failed to get product")
                config = mark_as_error(config, index)
                index += 1
                continue

            logger.info("Checking product")

            if first_run:
                try:
                    logger.info("First run")
                    click_popup_close_button(driver, wait)
                    confirm_age(driver, wait)
                    click_popup_close_button(driver, wait)
                    login(driver, wait, secret)
                    first_run = False
                    time.sleep(4)
                except:
                    logger.error("Unable to initialize first run.", exc_info=True)
                    break


            is_product_availible = check_if_availible(driver, wait)

            if is_product_availible:
                try:
                    add_to_cart(driver, wait)
                except Exception as e:
                    logger.error("Failed to add to cart. Maybe the product isn't availible. Checking again.")
                    try:
                        get_product(product, driver, wait)
                        if (check_if_availible(driver, wait)):
                            logger.info("Looks like product is still availible. Trying to add to cart again.")
                            add_to_cart(driver, wait)
                            logger.info("Successfully added to cart on retry")
                        else:
                            logger.info("Actually, the product is not availible.")
                            index += 1
                            continue
                    except:
                        logger.error("Failed to add to cart. Marking product as error", exc_info=True)
                        config = mark_as_error(config, index)
                        index += 1

                try:
                    checkout(driver, wait, secret)
                except Exception as e:
                    logger.error("Failed checkout. Trying again", exc_info=True)
                    try:
                        time.sleep(4)
                        get_product(product, driver, wait)
                        checkout(driver, wait, secret)
                    except:
                        logger.error("Failed checkout. Quitting", exc_info=True)
                        close(driver, wait)

                config = mark_as_purchased(config, index)

            index += 1  # Move to the next product
            logger.info("Moving to next product")
            time.sleep(4)

        # Reset index if all products have been checked
        if index >= product_count:
            index = 0  # Restart from the first product

        variability = random.uniform(-0.2, 0.2)  # Add or subtract up to 20% of retry_interval
        adjusted_sleep = retry_interval * (1 + variability)
        
        driver.quit()
        logger.info(f"Quit driver and waiting {adjusted_sleep/60} minutes")
        time.sleep(adjusted_sleep)



def get_product(product, driver, wait):
    product_url = product['url']
    name = product['name']

    if product_url is not None:
        logger.info(f"Loading URL {product_url}")
        driver.get(product_url)
    elif name is not None:
        logger.info(f"Searcing name {name}")
        load_home_page(driver, wait)
        confirm_age(driver, wait)
        search_for_product(name, driver, wait)
    else:
        logger.error("Product name or URL must be specified")
        driver.quit()

    time.sleep(4)


def login(driver, wait, secret):
    time.sleep(3)
    try:
        # Wait for the button to be clickable
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@class='modal-header-login link' and .//span[text()='Log In']]")))
        login_button.click()  # Click the button
        logger.info("Clicked login button")
    except:
        logger.error("Log In button did not become clickable in time.")

    time.sleep(3)

    email_input = wait.until(EC.visibility_of_element_located((By.ID, "authentication_header_login_form_email")))
    email_input.clear()  # Clear any existing text
    email_input.send_keys(secret['email'])

    password_input = wait.until(EC.visibility_of_element_located((By.ID, "authentication_header_login_form_password")))
    password_input.clear()  # Clear any existing text
    password_input.send_keys(secret['password'])

    time.sleep(3)

    try:
        final_login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and @aria-label='LOGIN']")))
        final_login_button.click()  # Click the button
        logger.info("Logged in successfully")
    except:
        logger.error("Error while logging in...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"login_error_{timestamp}.png")

        raise


def load_home_page(driver, wait):
    driver.get("https://finewineandgoodspirits.com")
    logger.info("Loaded home page")


def confirm_age(driver, wait):
    try:
        button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Yes, Enter into the site']")))
        button.click()
        logger.info("Age confirmed")
    except:
        pass


def search_for_product(name, driver, wait):
    try:
        input_field = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@aria-label='search']")))
        input_field.send_keys(name)
        input_field.send_keys(Keys.RETURN)
        logger.info(f"Searched for product: {name}")

        time.sleep(4)
        input_field = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, name)))
        link = driver.find_element(By.PARTIAL_LINK_TEXT, name)
        link.click()
        time.sleep(4)
    except:
        logger.error(f"Failed to search for {name}")
        raise


def check_if_availible(driver, wait):
    time.sleep(8)
    click_popup_close_button(driver, wait)
    try:
        # Wait for the button to be present in the DOM
        wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@class='pdp__info-quantity-availability']//button[@class='add-to-cart-button button full-width false' and text()='Coming Soon']")))
        logger.info("Product not yet availible")
        return False
    except:
        logger.info("Product appears to be in stock...")
        logger.info("Page source snapshot for debugging: \n" + driver.page_source)
        return True  # Button does not exist


def add_to_cart(driver, wait):
    time.sleep(3)

    click_popup_close_button(driver, wait)

    try:
        logger.info("Adding to cart")
        availability_button = wait.until(EC.element_to_be_clickable ((By.XPATH, "//button[@class='link' and text()='Click to see availability.']")))
        availability_button.click()
    except:
        logger.error("Error while checking availability...")

    time.sleep(3)
    click_popup_close_button(driver, wait)

    if PICKUP_METHOD == "IN_STORE":
        logger.info("Picking up in store.")
        try:
            ship_button = wait.until(EC.element_to_be_clickable ((By.XPATH, "//div[@role='dialog']//button[@class='button fulfillment ' and .//p[text()='Pick Up']]")))
            driver.execute_script("arguments[0].click();", ship_button)
        except:
            logger.error("Error while clicking pick up...")

        time.sleep(3)

        try:
            search_input = wait.until(EC.visibility_of_element_located((By.NAME, "fulltext")))
            search_input.clear()  # Clear any existing text
            search_input.send_keys(STORE_ZIP_CODE)  # Enter the search value
        except:
            logger.error("Error while searching for store...")

    elif PICKUP_METHOD == "SHIP":
        logger.info("Shipping.")
        try:
            ship_button = wait.until(EC.element_to_be_clickable((
                By.XPATH, 
                "//div[h4[@id='fulfillmentMethod' and text()='How would you like to shop?']]//button[@class='button fulfillment ' and .//p[@class='fulfillment' and text()='Ship'] and .//p[@class='small' and text()='To Me or My Store']]"
            )))            
            ship_button.click()
            logger.info("Clicked ship")
        except:
            # logger.info("Page source snapshot for debugging: \n" + driver.page_source)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            driver.save_screenshot(f"shipping_error_{timestamp}.png")
            logger.error("Error while clicking ship...")
    else:
        logger.error("Unsupported shipping method. Must be either IN_STORE or SHIP")

    time.sleep(3)

    click_popup_close_button(driver, wait)
    try:
        add_to_cart_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='pdp__info-quantity-availability']//button[@class='add-to-cart-button button full-width false']")))
        add_to_cart_button.click()
        logger.info("Added to cart.")
    except:
        logger.error("Error while adding to cart...")
        raise()
    
    time.sleep(3)


def checkout(driver, wait, secret):
    logger.info("Checking out")

    time.sleep(6)

    click_popup_close_button(driver, wait)

    try:
        driver.get("https://www.finewineandgoodspirits.com/checkout")
        logger.info("Navigated to checkout")
    except:
        logger.error("Failed to navigate to checkout page")

    time.sleep(4)

    click_popup_close_button(driver, wait)

    if SHIP_METHOD == "MY_STORE":
        try:
            # Wait for the radio button to be present and clickable
            my_store_button = wait.until(EC.element_to_be_clickable((By.ID, "shipToMyStore")))
            my_store_button.click()  # Click the radio button to select it
            logger.info("Ship to My Store radio button selected.")
        except:
            logger.error("Ship to My Store radio button did not become clickable in time.")
            raise

        time.sleep(3)

        click_popup_close_button(driver, wait)

        try:
            # Wait for the button to be clickable
            continue_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Continue to Payment']")))
            continue_button.click()  # Click the button
            logger.info("Continue to Payment button clicked.")
        except:
            logger.error("Continue to Payment button did not become clickable in time.")
            raise


    time.sleep(6)

    click_popup_close_button(driver, wait)
    
    try:
        security_code_input = wait.until(EC.visibility_of_element_located((By.ID, "csv-code")))
        security_code_input.clear()  # Clear any existing text
        security_code_input.send_keys(secret['cvv']) # Enter the security code
        logger.info("Entered security code")
    except:
        logger.error("Failed entering security code...")
        raise

    time.sleep(4)

    click_popup_close_button(driver, wait)

    try:
        place_order_button = wait.until(EC.element_to_be_clickable((By.ID, "place-order-button")))
        # place_order_button.click()
        logger.info("Placed order")
    except:
        logger.error("Failed to place order")
        raise

    time.sleep(5)


def click_popup_close_button(driver, wait):
    try:
        close_button = driver.find_element(By.CLASS_NAME, "ltkpopup-close")
        close_button.click()
        logger.info("Popup close button clicked.")
        time.sleep(2)
    except:
        pass


def close(driver, wait):
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
        logger.info("Retrieved secret")
    except Exception as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    return json.loads(get_secret_value_response['SecretString'])

def mark_as_purchased(config, index):
    config['products'][index]['status'] = 'purchased'
    logger.info(f"Inserting config: {config}")
    insert_configuration("PurchaseBot", config)
    return config


def mark_as_error(config, index):
    config['products'][index]['status'] = 'error'
    logger.info(f"Inserting config: {config}")
    insert_configuration("PurchaseBot", config)
    return config

start_bot()