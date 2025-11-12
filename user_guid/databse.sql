-- Create Database (optional)
CREATE DATABASE IF NOT EXISTS cybercafe_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cybercafe_app;

-- ----------------------------
-- Table structure for `admins`
-- ----------------------------
CREATE TABLE IF NOT EXISTS admins (
  id INT NOT NULL AUTO_INCREMENT,
  full_name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  contact VARCHAR(15) NOT NULL,
  password TEXT NOT NULL,
  profile_image TEXT DEFAULT NULL,
  gender_id INT DEFAULT 1,
  role ENUM('owner', 'admin', 'seller') DEFAULT 'admin',
  address TEXT DEFAULT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------
-- Table structure for `users`
-- ----------------------------
CREATE TABLE IF NOT EXISTS users (
  id INT NOT NULL AUTO_INCREMENT,
  full_name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  contact VARCHAR(15) NOT NULL,
  password TEXT NOT NULL,
  profile_image TEXT DEFAULT NULL,
  gender_id INT DEFAULT 1,
  role ENUM('user', 'admin', 'owner') DEFAULT 'user',
  address TEXT DEFAULT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------
-- Table structure for `products`
-- ----------------------------
CREATE TABLE IF NOT EXISTS products (
  id INT NOT NULL AUTO_INCREMENT,
  name TEXT NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  discount_price DECIMAL(10,2) DEFAULT NULL,
  images JSON DEFAULT NULL,
  description TEXT DEFAULT NULL,
  seller_id INT DEFAULT NULL,
  is_visible TINYINT(1) DEFAULT 1,
  PRIMARY KEY (id),
  INDEX (seller_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------
-- Table structure for `movies`
-- ----------------------------
CREATE TABLE IF NOT EXISTS movies (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(255) DEFAULT NULL,
  price DECIMAL(10,2) DEFAULT NULL,
  discount_price DECIMAL(10,2) DEFAULT NULL,
  images JSON DEFAULT NULL,
  description TEXT DEFAULT NULL,
  link1 TEXT DEFAULT NULL,
  seller_id INT DEFAULT NULL,
  link2 TEXT DEFAULT NULL,
  link3 TEXT DEFAULT NULL,
  link4 TEXT DEFAULT NULL,
  created_at DATETIME DEFAULT NULL,
  is_visible TINYINT(1) DEFAULT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------
-- Table structure for `carts`
-- ----------------------------
CREATE TABLE IF NOT EXISTS carts (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX (user_id),
  INDEX (product_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------
-- Table structure for `orders`
-- ----------------------------
CREATE TABLE IF NOT EXISTS orders (
  id INT NOT NULL AUTO_INCREMENT,
  item_id INT NOT NULL,
  item_name VARCHAR(255) NOT NULL,
  quantity INT NOT NULL DEFAULT 1,
  amount DECIMAL(10,2) NOT NULL,
  status ENUM('pending', 'accepted', 'cancelled', 'delivered') DEFAULT 'pending',
  image VARCHAR(255) DEFAULT NULL,
  address1 TEXT DEFAULT NULL,
  address2 TEXT DEFAULT NULL,
  city VARCHAR(100) DEFAULT NULL,
  pincode VARCHAR(10) DEFAULT NULL,
  order_date VARCHAR(50) DEFAULT NULL,
  is_paid TINYINT(1) DEFAULT 0,
  user_id INT DEFAULT NULL,
  user_email VARCHAR(150) DEFAULT NULL,
  user_name VARCHAR(100) DEFAULT NULL,
  user_contact VARCHAR(20) DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  accepted_at DATETIME DEFAULT NULL,
  cancelled_at DATETIME DEFAULT NULL,
  delivered_at DATETIME DEFAULT NULL,
  seller_id INT DEFAULT NULL,
  payment_id VARCHAR(100) DEFAULT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------
-- Table structure for `morders`
-- ----------------------------
CREATE TABLE IF NOT EXISTS morders (
  id INT NOT NULL AUTO_INCREMENT,
  item_id INT NOT NULL,
  item_name VARCHAR(255) NOT NULL,
  quantity INT DEFAULT 1,
  amount DECIMAL(10,2) DEFAULT 0.00,
  status VARCHAR(50) DEFAULT 'pending',
  image VARCHAR(255) DEFAULT NULL,
  link1 TEXT DEFAULT NULL,
  order_date VARCHAR(100) DEFAULT NULL,
  is_paid TINYINT(1) DEFAULT 0,
  user_id INT DEFAULT NULL,
  user_email VARCHAR(255) DEFAULT NULL,
  user_name VARCHAR(255) DEFAULT NULL,
  user_contact VARCHAR(50) DEFAULT NULL,
  created_at VARCHAR(100) DEFAULT NULL,
  accepted_at VARCHAR(100) DEFAULT NULL,
  cancelled_at VARCHAR(100) DEFAULT NULL,
  delivered_at VARCHAR(100) DEFAULT NULL,
  seller_id INT DEFAULT NULL,
  payment_id VARCHAR(100) DEFAULT NULL,
  link2 TEXT DEFAULT NULL,
  link3 TEXT DEFAULT NULL,
  link4 TEXT DEFAULT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------
-- Table structure for `visits`
-- ----------------------------
CREATE TABLE IF NOT EXISTS visits (
  id INT NOT NULL AUTO_INCREMENT,
  ip VARCHAR(100) NOT NULL,
  user_agent TEXT DEFAULT NULL,
  page VARCHAR(255) DEFAULT NULL,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;