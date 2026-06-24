-- ==========================================================================
--  Spotify-clone database schema  (MySQL / MariaDB — XAMPP)
-- --------------------------------------------------------------------------
--  This file is OPTIONAL.  The easiest setup is just:  python seed.py
--  (which creates the database, the tables AND the sample data for you).
--
--  Use this file only if you prefer to create the schema by hand in
--  phpMyAdmin:  open phpMyAdmin -> Import -> choose this file -> Go,
--  then run  `python seed.py`  to fill it with sample data.
-- ==========================================================================

CREATE DATABASE IF NOT EXISTS `elite_minus`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `elite_minus`;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `play_history`;
DROP TABLE IF EXISTS `playlist_songs`;
DROP TABLE IF EXISTS `liked_songs`;
DROP TABLE IF EXISTS `followed_artists`;
DROP TABLE IF EXISTS `playlists`;
DROP TABLE IF EXISTS `songs`;
DROP TABLE IF EXISTS `albums`;
DROP TABLE IF EXISTS `artists`;
DROP TABLE IF EXISTS `users`;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE `users` (
  `id`            INT AUTO_INCREMENT PRIMARY KEY,
  `username`      VARCHAR(50)  NOT NULL UNIQUE,
  `email`         VARCHAR(120) NOT NULL UNIQUE,
  `password_hash` VARCHAR(255) NOT NULL,
  `display_name`  VARCHAR(80),
  `is_admin`      BOOLEAN NOT NULL DEFAULT 0,
  `created_at`    DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE `artists` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `name`              VARCHAR(120) NOT NULL,
  `bio`               TEXT,
  `genre`             VARCHAR(60),
  `monthly_listeners` INT DEFAULT 0,
  `image_seed`        VARCHAR(120),
  INDEX `ix_artists_name` (`name`)
) ENGINE=InnoDB;

CREATE TABLE `albums` (
  `id`           INT AUTO_INCREMENT PRIMARY KEY,
  `title`        VARCHAR(150) NOT NULL,
  `artist_id`    INT,
  `release_date` DATE,
  `cover_seed`   VARCHAR(120),
  INDEX `ix_albums_title` (`title`),
  FOREIGN KEY (`artist_id`) REFERENCES `artists`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE `songs` (
  `id`           INT AUTO_INCREMENT PRIMARY KEY,
  `title`        VARCHAR(150) NOT NULL,
  `artist_id`    INT,
  `album_id`     INT,
  `track_number` INT DEFAULT 1,
  `duration`     INT DEFAULT 0,
  `audio_url`    VARCHAR(500) NOT NULL,
  `play_count`   INT DEFAULT 0,
  INDEX `ix_songs_title` (`title`),
  FOREIGN KEY (`artist_id`) REFERENCES `artists`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`album_id`)  REFERENCES `albums`(`id`)  ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE `playlists` (
  `id`          INT AUTO_INCREMENT PRIMARY KEY,
  `owner_id`    INT,
  `name`        VARCHAR(120) NOT NULL,
  `description` VARCHAR(300),
  `cover_seed`  VARCHAR(120),
  `is_public`   BOOLEAN DEFAULT TRUE,
  `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`owner_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE `playlist_songs` (
  `playlist_id` INT NOT NULL,
  `song_id`     INT NOT NULL,
  `position`    INT NOT NULL DEFAULT 0,
  `added_at`    DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`playlist_id`, `song_id`),
  FOREIGN KEY (`playlist_id`) REFERENCES `playlists`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`song_id`)     REFERENCES `songs`(`id`)     ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE `liked_songs` (
  `user_id`  INT NOT NULL,
  `song_id`  INT NOT NULL,
  `liked_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`, `song_id`),
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`song_id`) REFERENCES `songs`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE `followed_artists` (
  `user_id`     INT NOT NULL,
  `artist_id`   INT NOT NULL,
  `followed_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`, `artist_id`),
  FOREIGN KEY (`user_id`)   REFERENCES `users`(`id`)   ON DELETE CASCADE,
  FOREIGN KEY (`artist_id`) REFERENCES `artists`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE `play_history` (
  `id`        INT AUTO_INCREMENT PRIMARY KEY,
  `user_id`   INT,
  `song_id`   INT,
  `played_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_history_user` (`user_id`),
  INDEX `ix_history_played` (`played_at`),
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`song_id`) REFERENCES `songs`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;
