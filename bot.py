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


################################################################
#                           TO DO                              #
################################################################
# TODO: Fix searching
# TODO: Add max price to website configuration
################################################################


################################################################
#                       CONFIGURATION                          #
################################################################
PICKUP_METHOD = "SHIP" # "IN_STORE" or "SHIP"
SHIP_METHOD = "MY_ADDRESS" # "MY_ADDRESS" or "MY_STORE"
STORE_ZIP_CODE = 17363
MAX_PRICE = 275
################################################################
################################################################


logging.basicConfig(
    filename='./logs/app.log',
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
    logger.info("Version 24.11.11.21.26")
    is_product_availible = False
    product_count = 1
    index = 0  # Initialize the index

    while product_count > 0:
        first_run = True
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_window_size(1920, 1080)

        wait = WebDriverWait(driver, 10)
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
                except:
                    logger.error("Unable to initialize first run.", exc_info=True)
                    break


            is_product_availible = check_if_availible(driver, wait)

            if is_product_availible:
                try:
                    add_to_cart(driver, wait)
                except:
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
                        continue

                checkout_success = False

                try:
                    checkout_success = checkout(driver, wait, secret)
                except:
                    logger.error("Failed checkout. Trying again", exc_info=True)
                    try:
                        time.sleep(4)
                        get_product(product, driver, wait)
                        checkout_success = checkout(driver, wait, secret)
                    except:
                        logger.error("Failed checkout again.", exc_info=True)

                if (checkout_success):
                    config = mark_as_purchased(config, index)
                else:
                    config = mark_as_error(config, index)

            index += 1  # Move to the next product
            logger.info("Moving to next product")
            time.sleep(2)

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
        logger.info(f"Got product")
    elif name is not None:
        logger.info(f"Searcing name {name}")
        load_home_page(driver, wait)
        confirm_age(driver, wait)
        search_for_product(name, driver, wait)
    else:
        logger.error("Product name or URL must be specified")
        driver.quit()

    time.sleep(1)

def login(driver, wait, secret):
    time.sleep(2)
    click_popup_close_button(driver, wait)
    try:
        # Wait for the button to be clickable
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Log In') or .//span[contains(text(), 'Log In')]]")))
        login_button.click()  # Click the button
        logger.info("Clicked login button")
    except:
        logger.error("Log In button did not become clickable in time.")

    time.sleep(1)

    email_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@class='LoginForm']//form[@aria-label='Login Form']//input[@type='email' and contains(@id, 'login_form_email') and @name='email']")))
    email_input.clear()  # Clear any existing text
    email_input.send_keys(secret['email'])

    password_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@class='LoginForm']//form[@aria-label='Login Form']//input[@type='password' and contains(@id, 'login_form_password')]")))
    password_input.clear()  # Clear any existing text
    password_input.send_keys(secret['password'])

    time.sleep(1)

    try:
        final_login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and @aria-label='LOGIN']")))
        final_login_button.click()  # Click the button
        logger.info("Logged in successfully")
    except:
        logger.error("Error while logging in...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"screenshots/login_error_{timestamp}.png")
        raise


def load_home_page(driver, wait):
    driver.get("https://finewineandgoodspirits.com")
    logger.info("Loaded home page")


def confirm_age(driver, wait):
    try:
        button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Yes, Enter into the site']")))
        button.click()
        logger.info("Age confirmed")
        time.sleep(1)
    except:
        pass


def search_for_product(name, driver, wait):
    try:
        input_field = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@aria-label='search']")))
        input_field.send_keys(name)
        input_field.send_keys(Keys.RETURN)
        logger.info(f"Searched for product: {name}")

        time.sleep(2)
        input_field = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, name)))
        link = driver.find_element(By.PARTIAL_LINK_TEXT, name)
        link.click()
    except:
        logger.error(f"Failed to search for {name}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"screenshots/search_error_{timestamp}.png")
        raise


def check_if_availible(driver, wait):
    click_popup_close_button(driver, wait)
    try:
        # Wait for the button to be present in the DOM
        wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@class='pdp__info-quantity-availability']//button[@class='add-to-cart-button button full-width false' and text()='Coming Soon']")))
        logger.info("Product not yet availible")
        return False
    except:
        logger.info("Product appears to be in stock...")
        return True  # Button does not exist


def add_to_cart(driver, wait):
    click_popup_close_button(driver, wait)
    short_wait = WebDriverWait(driver, 3)

    try:
        logger.info("Adding to cart")
        availability_button = short_wait.until(EC.element_to_be_clickable ((By.XPATH, "//button[@class='link' and text()='Click to see availability.']")))
        availability_button.click()
    except:
        logger.warn("Error while checking availability...")

    time.sleep(1)
    click_popup_close_button(driver, wait)

    if PICKUP_METHOD == "IN_STORE":
        logger.info("Picking up in store.")
        try:
            ship_button = wait.until(EC.element_to_be_clickable ((By.XPATH, "//div[@role='dialog']//button[@class='button fulfillment ' and .//p[text()='Pick Up']]")))
            driver.execute_script("arguments[0].click();", ship_button)
        except:
            logger.warn("Error while clicking pick up...")

        try:
            search_input = wait.until(EC.visibility_of_element_located((By.NAME, "fulltext")))
            search_input.clear()
            search_input.send_keys(STORE_ZIP_CODE)
        except:
            logger.error("Error while searching for store...")

    elif PICKUP_METHOD == "SHIP":
        logger.info("Shipping.")
        try:
            ship_button = short_wait.until(EC.element_to_be_clickable((
                By.XPATH, 
                "//div[h4[@id='fulfillmentMethod' and text()='How would you like to shop?']]//button[@class='button fulfillment ' and .//p[@class='fulfillment' and text()='Ship'] and .//p[@class='small' and text()='To Me or My Store']]"
            )))            
            ship_button.click()
            logger.info("Clicked ship")
        except:
            # logger.info("Page source snapshot for debugging: \n" + driver.page_source)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            driver.save_screenshot(f"screenshots/shipping_error_{timestamp}.png")
            logger.warn("Error while clicking ship...")
    else:
        logger.error("Unsupported shipping method. Must be either IN_STORE or SHIP")

    time.sleep(1)
    click_popup_close_button(driver, wait)
    try:
        add_to_cart_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='pdp__info-quantity-availability']//button[@class='add-to-cart-button button full-width false']")))
        add_to_cart_button.click()
        logger.info("Added to cart.")
    except:
        logger.error("Error while adding to cart...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"screenshots/add_to_cart_error_{timestamp}.png")
        raise()
    
    time.sleep(1)    
    
    try:
        # Wait until the loading icon is no longer visible or removed
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "span.icon--after.icon-loading")))
        logger.info("Loading icon has disappeared.")
    except:
        logger.info("Timeout: Loading icon is still present.")

    time.sleep(1)    

def checkout(driver, wait, secret):
    logger.info("Checking out")
    short_wait = WebDriverWait(driver, 2)

    click_popup_close_button(driver, wait)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    driver.save_screenshot(f"screenshots/checkout_issue_pre_checkout_{timestamp}.png")

    try:
        driver.get("https://www.finewineandgoodspirits.com/checkout")
        logger.info("Navigated to checkout")
    except:
        logger.error("Failed to navigate to checkout page")

    time.sleep(10)
    click_popup_close_button(driver, wait)

    try:
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Log Out') or .//span[contains(text(), 'Log Out')]]")))
    except:
        logger.warn("Log Out button not found. Logging in.")
        login(driver, wait, secret)
        logger.info("Logged in.")
        time.sleep(10)

    click_popup_close_button(driver, wait)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    driver.save_screenshot(f"screenshots/checkout_issue_in_checkout_page_{timestamp}.png")


    if SHIP_METHOD == "MY_STORE":
        try:
            # Wait for the radio button to be present and clickable
            my_store_button = wait.until(EC.element_to_be_clickable((By.ID, "shipToMyStore")))
            my_store_button.click()  # Click the radio button to select it
            logger.info("Ship to My Store radio button selected.")
            time.sleep(1)
        except:
            logger.warn("Ship to My Store radio button did not become clickable in time.")
            raise

        click_popup_close_button(driver, wait)
    elif SHIP_METHOD == "MY_ADDRESS":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"screenshots/checkout_issue_ship_to_my_address_{timestamp}.png")
        try:
            # Wait for the radio button to be present and clickable
            my_address_button = short_wait.until(EC.element_to_be_clickable((By.ID, "shipToMyAddress")))
            my_address_button.click()  # Click the radio button to select it
            logger.info("Ship to My Address radio button selected.")
        except:
            logger.warn("Ship to My Address radio button did not become clickable in time.")
    else:
        logger.error(f"Unsupported ship method: {SHIP_METHOD}")
        raise NotImplementedError

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    driver.save_screenshot(f"screenshots/checkout_issue_continue_to_payment_{timestamp}.png")

    try:
        # Wait for the button to be clickable
        continue_button = short_wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Continue to Payment']")))
        continue_button.click()  # Click the button
        logger.info("Continue to Payment button clicked.")
    except:
        logger.warn("Continue to Payment button did not become clickable in time.")

    time.sleep(1)
    click_popup_close_button(driver, wait)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    driver.save_screenshot(f"screenshots/checkout_issue_check_price_{timestamp}.png")

    if not is_valid_price(driver, wait):
        empty_cart(driver, wait)
        return False
    
    click_popup_close_button(driver, wait)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    driver.save_screenshot(f"screenshots/checkout_issue_enter_security_code_{timestamp}.png")
    try:
        security_code_input = wait.until(EC.visibility_of_element_located((By.ID, "csv-code")))
        security_code_input.clear()  # Clear any existing text
        security_code_input.send_keys(secret['cvv']) # Enter the security code
        logger.info("Entered security code")
    except:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"screenshots/security_code_error_{timestamp}.png")
        logger.error("Failed entering security code...")
        raise

    time.sleep(1)
    click_popup_close_button(driver, wait)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    driver.save_screenshot(f"screenshots/checkout_issue_placing_order_{timestamp}.png")

    try:
        place_order_button = wait.until(EC.element_to_be_clickable((By.ID, "place-order-button")))
        # place_order_button.click()
        logger.info("Placed order")
    except:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"screenshots/place_order_error_{timestamp}.png")
        logger.error("Failed to place order")
        raise

    time.sleep(5)
    return True


def is_valid_price(driver, wait):
    price_value = 9999
    try:
        price_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "h4.order-summary-value.orderSummary-price")))
        price_value = float(price_element.text)
        logger.info(f"Found price of {price_value}")
    except:
        logger.error("Cannot get price")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        driver.save_screenshot(f"screenshots/get_price_error_{timestamp}.png")
        raise

    if price_value > MAX_PRICE:
        logger.info(f"Price, {price_value}, is above max price of {MAX_PRICE}")
        return False
    else:
        logger.info(f"Price, {price_value}, is below max price of {MAX_PRICE}")
        return True
    

def empty_cart(driver, wait):
    logger.info("Emptying cart")
    load_home_page(driver, wait)

    time.sleep(1)
    click_popup_close_button(driver, wait)

    try:
        # Wait until the cart button is clickable
        cart_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.miniCart__openButton.icon--before.icon-cart")))
        cart_button.click()
        logger.info("Clicked the cart button.")
    except:
        logger.error("Cart button not found or not clickable within the wait time.")
        return

    while True:
        try:
            delete_buttons = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "span.icon--before.icon-delete")))

            if not delete_buttons:
                logger.info("No delete buttons found.")
                break  # No delete buttons, break the loop

            # Click each delete button
            for button in delete_buttons:
                button.click()
                time.sleep(1)  # Add a short pause between clicks

            logger.info(f"Clicked {len(delete_buttons)} delete buttons.")

        except:
            logger.info("No more delete buttons within the wait time.")
            break  # Exit loop if no delete buttons found within 10 seconds

    logger.info("Cart has been emptied.")


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
    logger.info("Marking as purchased")
    config['products'][index]['status'] = 'purchased'
    logger.info(f"Inserting config: {config}")
    insert_configuration("PurchaseBot", config)
    return config


def mark_as_error(config, index):
    logger.info("Marking as error")
    config['products'][index]['status'] = 'error'
    logger.info(f"Inserting config: {config}")
    insert_configuration("PurchaseBot", config)
    return config

start_bot()