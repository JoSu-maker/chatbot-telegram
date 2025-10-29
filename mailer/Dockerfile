FROM php:8.2-apache

# Install system deps for Composer and ZIP
RUN apt-get update \
    && apt-get install -y --no-install-recommends git unzip libzip-dev curl \
       libpng-dev libjpeg62-turbo-dev libfreetype6-dev \
    && docker-php-ext-install zip \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install gd \
    && rm -rf /var/lib/apt/lists/*

# Install Composer
RUN php -r "copy('https://getcomposer.org/installer', 'composer-setup.php');" \
    && php composer-setup.php --install-dir=/usr/local/bin --filename=composer \
    && rm composer-setup.php

# Configure Apache docroot to public/
ENV APACHE_DOCUMENT_ROOT=/var/www/html/public
RUN sed -ri -e 's!/var/www/html!${APACHE_DOCUMENT_ROOT}!g' /etc/apache2/sites-available/*.conf \
    && sed -ri -e 's!/var/www/!${APACHE_DOCUMENT_ROOT}!g' /etc/apache2/apache2.conf /etc/apache2/conf-available/*.conf

WORKDIR /var/www/html

# Copy composer files and install deps
COPY composer.json ./
RUN composer install --no-dev --prefer-dist --no-interaction

# Copy source
COPY public/ ./public/

EXPOSE 80

# Healthcheck simple: PHP responds on index
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fsS http://localhost/ || exit 1
