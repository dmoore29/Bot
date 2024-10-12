import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
import time


################################################################
#                       CONFIGURATION                          #
################################################################

# PRODUCT = "W L Weller Full Proof Straight"
PRODUCT = "Horse Soldier Straight Bourbon"
# PRODUCT_URL = "https://www.finewineandgoodspirits.com/w-l-weller-full-proof-straight-bourbon-single-barrel-selection/product/100038215"
PRODUCT_URL = "https://www.finewineandgoodspirits.com/bulleit-straight-bourbon/product/000009000"
# PRODUCT_URL = None

RETRY_TIME_IN_SECONDS = 10
EMAIL = "davidmoore777@icloud.com"
PASSWORD = "DavidTest1862!"
PHONE_NUMBER = 7171231234

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
driver = webdriver.Chrome(service=service)
wait = WebDriverWait(driver, 5)

def start_bot():
    is_product_availible = False
    first_run = True

    while not is_product_availible:
        get_product()

        if first_run:
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
                    get_product()
                    checkout()
                except:
                    logger.error("Failed checkout. Quitting")
                    logger.error(f"Exception: {e}")
                    close()
        time.sleep(RETRY_TIME_IN_SECONDS)

    driver.quit()
    # TODO: Handle logic to retry checkout


def get_product():
    if PRODUCT_URL is not None:
        driver.get(PRODUCT_URL)
        confirm_age()
    elif PRODUCT is not None:
        load_home_page()
        confirm_age()
        search_for_product()
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

    email_input = wait.until(EC.visibility_of_element_located((By.ID, "authentication_header_login_form_email")))
    email_input.clear()  # Clear any existing text
    email_input.send_keys(EMAIL)  # Enter the email address

    password_input = wait.until(EC.visibility_of_element_located((By.ID, "authentication_header_login_form_password")))
    password_input.clear()  # Clear any existing text
    password_input.send_keys(PASSWORD)  # Enter the email address

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


def search_for_product():
    input_field = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@aria-label='search']")))
    input_field.send_keys(PRODUCT)
    input_field.send_keys(Keys.RETURN)
    logger.info(f"Searched for product: {PRODUCT}")

    time.sleep(2)
    input_field = wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, PRODUCT)))
    link = driver.find_element(By.PARTIAL_LINK_TEXT, PRODUCT)
    link.click()
    time.sleep(2)


def check_if_availible():
    try:
        # Wait for the button to be present in the DOM
        wait.until(EC.presence_of_element_located((By.XPATH, "//button[@class='add-to-cart-button button full-width false' and text()='Coming Soon']")))
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

start_bot()