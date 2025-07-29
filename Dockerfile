FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Update the package list and install system dependencies
RUN apt-get update

# Copy the requirements file
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

CMD ["python", "-m", "bot.main"]